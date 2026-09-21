"""
BTC 5M Smart Stop-Loss & Adaptive Exit Manager.

Implements a confirmation-based exit system separating:
1. TEMPORARY MARKET NOISE -> HOLD and re-analyze.
2. CONFIRMED THESIS FAILURE -> CONFIRMED_EXIT.
3. HARD RISK BREACH -> IMMEDIATE HARD_EXIT.

Enforces:
- Non-negotiable hard safety stops.
- Strict thesis immutability (locked prediction never flips).
- Time-aware and volatility-aware confirmation.
- Executable CLOB price validation.
- Complete persistent audit trail.
"""
import logging
import math
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session
from app.db.models import BTC5MTrade, BTC5MExitAudit

logger = logging.getLogger(__name__)

# Default confirmation and risk parameters
DEFAULT_SOFT_STOP_CONFIRMATION_SECONDS = 10.0
DEFAULT_THESIS_FAILURE_THRESHOLD = 60.0
DEFAULT_HARD_STOP_DELTA = 0.10  # Catastrophic distance below soft stop

# In-memory tracking of real peak prices observed during active trades
_trade_peak_prices: Dict[Any, float] = {}


def calculate_thesis_failure_score(
    trade: BTC5MTrade,
    btc_price: Optional[float],
    p2b: Optional[float],
    features: Dict[str, Any],
    time_remaining_sec: float
) -> Tuple[float, Dict[str, Any], str]:
    """
    Compute explicit Thesis Failure Score (0 to 100).
    A high score means the original locked thesis is genuinely invalidated.
    A low score means adverse price movement is temporary market noise.

    Breakdown:
    - BTC vs P2B Delta: up to 35 pts
    - Momentum Reversal: up to 20 pts
    - Fair Probability Collapse: up to 20 pts
    - Orderbook Imbalance Adverse Pressure: up to 15 pts
    - Time Remaining Urgency: up to 10 pts
    """
    locked_side = trade.locked_predicted_side or ("YES" if trade.side == "BUY" else "NO")
    breakdown = {
        "btc_vs_p2b": 0.0,
        "momentum": 0.0,
        "probability": 0.0,
        "orderbook": 0.0,
        "time_urgency": 0.0
    }
    reasons = []

    # 1. BTC vs Price-To-Beat Delta (Max 35 pts)
    # The primary fundamental anchor for a BTC 5M market
    if btc_price is not None and p2b is not None:
        p2b_diff = btc_price - p2b
        if locked_side == "YES":
            # Target is BTC > P2B
            if p2b_diff >= 0:
                # BTC is STILL above P2B! Thesis is fundamentally INTACT.
                breakdown["btc_vs_p2b"] = 0.0
            else:
                # BTC fell below P2B
                drop = abs(p2b_diff)
                pts = min(35.0, (drop / 25.0) * 35.0)
                breakdown["btc_vs_p2b"] = round(pts, 1)
                if pts >= 20.0:
                    reasons.append(f"BTC fell ${drop:.1f} below P2B")
        else:
            # Target is BTC < P2B (NO / DOWN)
            if p2b_diff <= 0:
                # BTC is STILL below P2B! Thesis is fundamentally INTACT.
                breakdown["btc_vs_p2b"] = 0.0
            else:
                # BTC surged above P2B
                surge = p2b_diff
                pts = min(35.0, (surge / 25.0) * 35.0)
                breakdown["btc_vs_p2b"] = round(pts, 1)
                if pts >= 20.0:
                    reasons.append(f"BTC rose ${surge:.1f} above P2B")

    # 2. Momentum Persistence / Reversal (Max 20 pts)
    spot_mom = features.get("btc_momentum_1m")
    ob_mom = features.get("short_momentum_1m", 0.0)
    effective_mom = spot_mom if spot_mom is not None else ob_mom

    if locked_side == "YES":
        if effective_mom is not None and effective_mom < -0.0003:  # Adverse downward momentum
            pts = min(20.0, abs(effective_mom) * 20000.0)
            breakdown["momentum"] = round(pts, 1)
            if pts >= 12.0:
                reasons.append("Persistent bearish momentum")
        else:
            breakdown["momentum"] = 0.0
    else:
        if effective_mom is not None and effective_mom > 0.0003:  # Adverse upward momentum
            pts = min(20.0, effective_mom * 20000.0)
            breakdown["momentum"] = round(pts, 1)
            if pts >= 12.0:
                reasons.append("Persistent bullish momentum")
        else:
            breakdown["momentum"] = 0.0

    # 3. Fair Probability Collapse (Max 20 pts)
    fair_yes = features.get("fair_prob_yes")
    if fair_yes is None:
        fair_yes = features.get("mid_price", 0.5)

    if locked_side == "YES":
        fair_prob = fair_yes
        if fair_prob is not None and fair_prob < 0.40:
            pts = min(20.0, (0.40 - fair_prob) * 50.0)
            breakdown["probability"] = round(pts, 1)
            if pts >= 12.0:
                reasons.append(f"Fair YES prob collapsed to {fair_prob*100:.1f}%")
        else:
            breakdown["probability"] = 0.0
    else:
        fair_prob = 1.0 - (fair_yes if fair_yes is not None else 0.5)
        if fair_prob < 0.40:
            pts = min(20.0, (0.40 - fair_prob) * 50.0)
            breakdown["probability"] = round(pts, 1)
            if pts >= 12.0:
                reasons.append(f"Fair NO prob collapsed to {fair_prob*100:.1f}%")
        else:
            breakdown["probability"] = 0.0

    # 4. Order Book Imbalance Adverse Pressure (Max 15 pts)
    imbalance = features.get("bid_ask_imbalance", 0.0)
    if locked_side == "YES":
        if imbalance is not None and imbalance < -0.20:  # Heavy sell pressure in CLOB
            pts = min(15.0, abs(imbalance) * 15.0)
            breakdown["orderbook"] = round(pts, 1)
            if pts >= 10.0:
                reasons.append("Heavy CLOB sell pressure")
        else:
            breakdown["orderbook"] = 0.0
    else:
        if imbalance is not None and imbalance > 0.20:  # Heavy buy pressure in CLOB
            pts = min(15.0, imbalance * 15.0)
            breakdown["orderbook"] = round(pts, 1)
            if pts >= 10.0:
                reasons.append("Heavy CLOB buy pressure")
        else:
            breakdown["orderbook"] = 0.0

    # 5. Time Remaining Urgency (Max 10 pts)
    # If < 45 seconds remain and BTC is on the adverse side of P2B, recovery is improbable
    try:
        t_rem = float(time_remaining_sec) if time_remaining_sec is not None else 0.0
    except (ValueError, TypeError):
        t_rem = 0.0

    btc_adverse = breakdown["btc_vs_p2b"] > 10.0
    if t_rem < 45.0 and btc_adverse:
        pts = min(10.0, ((45.0 - t_rem) / 45.0) * 10.0)
        breakdown["time_urgency"] = round(pts, 1)
        if pts >= 6.0:
            reasons.append(f"Improbable recovery with {t_rem:.0f}s left")
    else:
        breakdown["time_urgency"] = 0.0

    total_score = sum(breakdown.values())
    total_score = min(100.0, max(0.0, total_score))
    primary_reason = " | ".join(reasons) if reasons else "Adverse market pressure"

    return total_score, breakdown, primary_reason


class BTC5MExitManager:
    """
    Manages two-layer adaptive exits for active BTC5M trades.
    """

    def __init__(self, db: Session, instance_id: str = "instance_1"):
        self.db = db
        self.instance_id = instance_id

    def evaluate_exit(
        self,
        trade: BTC5MTrade,
        current_executable_price: Optional[float],
        current_mid_price: Optional[float],
        btc_price: Optional[float],
        p2b: Optional[float],
        features: Dict[str, Any],
        time_remaining_sec: float,
        risk_manager: Any,
        settings: Dict[str, Any]
    ) -> Tuple[str, Optional[float], str, float, Dict[str, Any], Optional[str]]:
        """
        Evaluate exit conditions for an active OPEN trade.

        Returns:
            decision: "HOLD" | "EXIT_REVIEW" | "CONFIRMED_EXIT" | "HARD_EXIT" | "TP"
            exit_price: float or None (executable CLOB price if closing)
            reason: str human-readable explanation
            thesis_failure_score: float (0 - 100)
            breakdown: dict factor breakdown
            audit_event: str or None (name of audit event to log)
        """
        now = datetime.now(timezone.utc)
        conf_seconds_total = float(settings.get("soft_stop_confirmation_seconds", DEFAULT_SOFT_STOP_CONFIRMATION_SECONDS))
        thesis_threshold = float(settings.get("thesis_failure_threshold", DEFAULT_THESIS_FAILURE_THRESHOLD))
        hard_stop_delta = float(settings.get("hard_stop_delta", DEFAULT_HARD_STOP_DELTA))

        try:
            t_rem = float(time_remaining_sec) if time_remaining_sec is not None else 0.0
        except (ValueError, TypeError):
            t_rem = 0.0

        # Dynamically shorten confirmation window late in candle (e.g. < 60s remaining)
        if t_rem < 60.0:
            conf_seconds_total = min(5.0, conf_seconds_total)

        # ── 1. HARD SAFETY STOPS (NON-NEGOTIABLE IMMEDIATE EXIT) ────────────────
        try:
            raw_hard = getattr(trade, "hard_stop_price", None)
            if raw_hard is not None and not isinstance(raw_hard, (int, float)):
                raw_hard = float(raw_hard)
        except (ValueError, TypeError):
            raw_hard = None

        try:
            raw_sl = getattr(trade, "stop_loss_price", None)
            if raw_sl is not None and not isinstance(raw_sl, (int, float)):
                raw_sl = float(raw_sl)
        except (ValueError, TypeError):
            raw_sl = 0.10

        hard_stop_price = raw_hard if raw_hard is not None else max(0.01, (raw_sl or 0.10) - hard_stop_delta)

        try:
            exec_p = float(current_executable_price) if current_executable_price is not None else None
        except (ValueError, TypeError):
            exec_p = None

        try:
            mid_p = float(current_mid_price) if current_mid_price is not None else None
        except (ValueError, TypeError):
            mid_p = None

        # A. Catastrophic price collapse below hard safety floor
        if exec_p is not None and exec_p <= hard_stop_price:
            reason = f"HARD SAFETY STOP breached: executable price ${exec_p:.4f} <= hard stop ${hard_stop_price:.4f}"
            return "HARD_EXIT", exec_p, reason, 100.0, {}, "HARD_STOP_TRIGGERED"

        # B. RiskManager limits (Daily Loss, Pause, or Circuit Breaker)
        if getattr(risk_manager, "is_paused", False):
            reason = "HARD SAFETY STOP: RiskManager circuit breaker active (trading paused)"
            return "HARD_EXIT", current_executable_price or trade.stop_loss_price, reason, 100.0, {}, "HARD_STOP_TRIGGERED"

        # C. Explicit Hard Safety Stop Loss
        sl_limit = float(settings.get("sl_dollar", 1.00))
        hard_cap_setting = float(settings.get("hard_cap_dollar", sl_limit))
        max_loss_cap = min(sl_limit, hard_cap_setting)
        early_cut = max_loss_cap * 0.85
        if exec_p is not None and trade.entry_price is not None and trade.quantity is not None:
            unrealized = (exec_p - float(trade.entry_price)) * float(trade.quantity)
            if unrealized <= -early_cut:
                reason = f"HARD SAFETY STOP breached: Loss -${abs(unrealized):.2f} hit early cut threshold -${early_cut:.2f} (Cap: -${max_loss_cap:.2f})"
                return "HARD_EXIT", exec_p, reason, 100.0, {}, "HARD_STOP_TRIGGERED"

            planned_r = float(trade.planned_risk) if trade.planned_risk else (float(trade.position_size) if trade.position_size else sl_limit)
            max_allowed_loss = max(planned_r, sl_limit) * 1.15
            if unrealized <= -max_allowed_loss:
                reason = f"HARD SAFETY STOP: Unrealized loss -${abs(unrealized):.2f} exceeded max trade boundary -${max_allowed_loss:.2f}"
                return "HARD_EXIT", exec_p, reason, 100.0, {}, "HARD_STOP_TRIGGERED"

        # ── 2. TAKE PROFIT TARGET ─────────────────────────────────────────────
        tp_target = float(settings.get("tp_dollar", 1.00))
        try:
            tp_p = float(trade.take_profit_price) if trade.take_profit_price is not None else None
        except (ValueError, TypeError):
            tp_p = None

        if exec_p is not None and trade.entry_price is not None and trade.quantity is not None:
            unrealized = (exec_p - float(trade.entry_price)) * float(trade.quantity)
            target_gain = float(trade.planned_reward) if (trade.planned_reward and float(trade.planned_reward) > 0) else tp_target
            if unrealized >= target_gain:
                reason = f"Take profit target reached: +${unrealized:.2f} >= +${target_gain:.2f}"
                return "TP", exec_p, reason, 0.0, {}, "TAKE_PROFIT"

            # ── 2A. INSTANT CENT-LEVEL PROFIT HARVESTER (OPTIONAL / TOGGLEABLE) ──
            enable_harvest = settings.get("enable_instant_harvest", False)
            if isinstance(enable_harvest, str):
                enable_harvest = enable_harvest.lower() in ("true", "1", "yes")
            min_harvest = float(settings.get("instant_profit_harvest_dollar", 0.0))
            if enable_harvest and min_harvest > 0.0 and unrealized >= min_harvest and exec_p > float(trade.entry_price):
                reason = f"INSTANT CENT PROFIT HARVEST: Market turned green +${unrealized:.2f} >= +${min_harvest:.2f} (Profit Collected)"
                return "TP", exec_p, reason, 0.0, {}, "TAKE_PROFIT"

        if tp_p is not None and exec_p is not None:
            if exec_p >= tp_p:
                reason = f"Take profit target reached: ${exec_p:.4f} >= ${tp_p:.4f}"
                return "TP", exec_p, reason, 0.0, {}, "TAKE_PROFIT"

        # ── 2B. TRAILING PROFIT & LOSS PROTECTION ──────────────────────────────
        if exec_p is not None and trade.entry_price is not None and trade.quantity is not None:
            unrealized = (exec_p - float(trade.entry_price)) * float(trade.quantity)
            trade_key = trade.id or id(trade)

            # Initialize peak price strictly to entry_price (NEVER use entry_target_price which is the TP target!)
            if trade_key not in _trade_peak_prices:
                _trade_peak_prices[trade_key] = float(trade.entry_price)

            if exec_p > _trade_peak_prices[trade_key]:
                _trade_peak_prices[trade_key] = exec_p

            peak_p = _trade_peak_prices[trade_key]
            peak_unrealized = (peak_p - float(trade.entry_price)) * float(trade.quantity)

            # SCALP RULE 1: Micro-Loss Cut (Only active if explicitly set below full SL limit)
            micro_loss_tolerance = float(settings.get("micro_loss_tolerance", sl_limit))
            # If sl_limit is >= 5.0 (e.g. $10 SL mode for reversal), do NOT cut prematurely on minor cents
            if sl_limit < 2.0 and micro_loss_tolerance < sl_limit and unrealized <= -micro_loss_tolerance:
                reason = f"MICRO LOSS CUT: Loss -${abs(unrealized):.2f} hit tolerance -${micro_loss_tolerance:.2f}"
                return "HARD_EXIT", exec_p, reason, 100.0, {}, "HARD_STOP_TRIGGERED"

            # SCALP RULE 2: Breakeven & Trailing Profit Locking
            be_trigger = float(settings.get("breakeven_trigger_dollar", 0.40))
            if peak_unrealized >= be_trigger and unrealized <= 0.10 and exec_p > float(trade.entry_price):
                reason = f"BREAKEVEN LOCKED: Capital protected +${unrealized:.2f} (Reversed from Peak +${peak_unrealized:.2f})"
                return "TP", exec_p, reason, 0.0, {}, "BREAKEVEN_STOP"

            # CRITICAL: Trailing Stop MUST NEVER lock in a negative loss!
            # It only locks if the trade climbed near the target (>= +$0.70) and secures positive gain (>= +$0.25)
            if peak_unrealized >= 0.70 and unrealized >= 0.25:
                trailing_drop_allowance = 0.02
                trailing_sl_price = peak_p - (trailing_drop_allowance / max(0.1, float(trade.quantity)))
                if exec_p <= trailing_sl_price and exec_p > float(trade.entry_price) and unrealized > 0:
                    reason = f"PROFIT LOCKED: Captured profit +${unrealized:.2f} (Reversed from Peak ${peak_p:.4f})"
                    return "TP", exec_p, reason, 0.0, {}, "TRAILING_STOP"

            # SCALP RULE 3: Adaptive Time Stop & Pre-Expiry Binary Trap Prevention
            max_hold_seconds = 240.0 if sl_limit >= 5.0 else 180.0
            if trade.entry_time is not None:
                trade_entry_dt = trade.entry_time
                if trade_entry_dt.tzinfo is None:
                    trade_entry_dt = trade_entry_dt.replace(tzinfo=timezone.utc)
                elapsed_seconds = (now - trade_entry_dt).total_seconds()
                # Pre-expiry exit: if negative and less than 45s left in candle, exit to avoid binary $0.00 collapse
                if t_rem <= 45.0 and unrealized < -0.20:
                    reason = f"PRE-EXPIRY CUT: Avoided binary zero collapse ({t_rem:.0f}s left in candle, loss limited to -${abs(unrealized):.2f})"
                    return "HARD_EXIT", exec_p, reason, 100.0, {}, "PRE_EXPIRY_STOP"
                if elapsed_seconds > max_hold_seconds or t_rem < 20.0:
                    reason = f"TIME STOP: Window expiry ({elapsed_seconds:.0f}s elapsed, {t_rem:.0f}s left in candle)"
                    return "HARD_EXIT", exec_p, reason, 100.0, {}, "TIME_STOP_TRIGGERED"

        # ── 3. COMPUTE THESIS FAILURE SCORE ────────────────────────────────────
        thesis_score, breakdown, primary_reason = calculate_thesis_failure_score(
            trade=trade,
            btc_price=btc_price,
            p2b=p2b,
            features=features,
            time_remaining_sec=time_remaining_sec
        )

        # ── 4. TWO-LAYER SOFT STOP / DYNAMIC SL / THESIS REVIEW ────────────────
        dynamic_sl_delta = float(settings.get("dynamic_sl_delta", 0.20))
        try:
            raw_sl = float(trade.stop_loss_price) if trade.stop_loss_price is not None else 0.20
            if trade.entry_price is not None:
                # Dynamic SL ensures stop is capped at entry_price - dynamic_sl_delta (e.g. $0.20 below entry)
                soft_stop_price = max(float(trade.entry_price) - dynamic_sl_delta, raw_sl)
            else:
                soft_stop_price = raw_sl
        except (ValueError, TypeError):
            soft_stop_price = 0.20

        # Check if price or thesis is in adverse review territory:
        # Either price is touching soft stop OR thesis has materially failed (thesis_score >= threshold)
        is_adverse = False
        if exec_p is not None and exec_p <= soft_stop_price:
            is_adverse = True
        elif mid_p is not None and mid_p <= (soft_stop_price + 0.02):
            is_adverse = True
        elif thesis_score >= thesis_threshold:
            is_adverse = True

        current_state = trade.exit_decision_state or "HOLD"

        # Scenario A: Neither price nor thesis is adverse (Normal market condition)
        if not is_adverse:
            if current_state == "EXIT_REVIEW":
                # Conditions recovered! Transition back to HOLD
                trade.exit_decision_state = "HOLD"
                trade.last_exit_review_reason = "Conditions recovered above adverse threshold"
                reason = f"THESIS STILL VALID — HOLDING (Price recovered to ${current_executable_price:.4f})"
                return "HOLD", None, reason, thesis_score, breakdown, "EXIT_REVIEW_HOLD"
            else:
                trade.exit_decision_state = "HOLD"
                return "HOLD", None, "Thesis active — normal holding", thesis_score, breakdown, None

        # Scenario B: Adverse condition detected (Price below soft stop OR thesis failed)
        # Enter or continue EXIT_REVIEW
        if current_state != "EXIT_REVIEW":
            # First time adverse condition is detected!
            trade.exit_decision_state = "EXIT_REVIEW"
            trade.soft_stop_touched_at = now
            trade.exit_review_started_at = now
            trade.thesis_failure_score = thesis_score
            trigger_detail = f"Thesis failure score {thesis_score:.1f} >= {thesis_threshold:.0f}" if thesis_score >= thesis_threshold else f"Soft stop touched (${current_executable_price:.4f} <= ${soft_stop_price:.4f})"
            reason = f"{trigger_detail}; entering EXIT_REVIEW confirmation period ({conf_seconds_total:.0f}s)"
            trade.last_exit_review_reason = reason
            return "EXIT_REVIEW", None, reason, thesis_score, breakdown, "SOFT_STOP_TOUCHED"

        # Currently in EXIT_REVIEW: Check confirmation window
        started_at = trade.exit_review_started_at or now
        # Strip tzinfo if naive
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        elapsed_seconds = (now - started_at).total_seconds()

        trade.thesis_failure_score = thesis_score

        if elapsed_seconds < conf_seconds_total:
            # Still in grace / confirmation window: Do NOT exit prematurely
            reason = (
                f"EXIT_REVIEW: Analyzing temporary noise vs thesis failure "
                f"({elapsed_seconds:.0f}s / {conf_seconds_total:.0f}s elapsed | Score: {thesis_score:.1f}/100)"
            )
            trade.last_exit_review_reason = reason
            return "EXIT_REVIEW", None, reason, thesis_score, breakdown, None

        # Confirmation window has elapsed (>= conf_seconds_total): Decision time!
        if thesis_score >= thesis_threshold:
            # Thesis has genuinely and materially failed!
            trade.exit_decision_state = "CONFIRMED_EXIT"
            exit_price = current_executable_price or trade.stop_loss_price
            reason = (
                f"CONFIRMED_EXIT: Original {trade.locked_predicted_side} thesis materially invalidated "
                f"(Score {thesis_score:.1f} >= {thesis_threshold:.1f}: {primary_reason})"
            )
            trade.last_exit_review_reason = reason
            return "CONFIRMED_EXIT", exit_price, reason, thesis_score, breakdown, "EXIT_REVIEW_CONFIRMED"
        else:
            # Confirmation window expired BUT thesis failure score is LOW (< threshold)!
            # This is TEMPORARY MARKET NOISE (e.g. BTC is still above P2B for YES).
            # HOLD the position and protect from premature exit!
            trade.exit_decision_state = "HOLD"
            reason = (
                f"THESIS STILL VALID — HOLDING: Market noise detected. Thesis score {thesis_score:.1f} < {thesis_threshold:.1f} "
                f"(BTC vs P2B intact) — continuing to hold position."
            )
            trade.last_exit_review_reason = reason
            # Reset review timer so future drops get fresh grace
            trade.exit_review_started_at = None
            return "HOLD", None, reason, thesis_score, breakdown, "EXIT_REVIEW_HOLD"

    def record_audit(
        self,
        trade: BTC5MTrade,
        event_type: str,
        current_executable_price: Optional[float],
        btc_price: Optional[float],
        p2b: Optional[float],
        features: Dict[str, Any],
        time_remaining_sec: float,
        current_exit_decision: str,
        thesis_failure_score: float,
        reason: str,
        breakdown: Dict[str, Any]
    ) -> BTC5MExitAudit:
        """
        Write a persistent audit record into btc5m_exit_audits.
        """
        now = datetime.now(timezone.utc)
        curr_p = current_executable_price or trade.entry_price or 0.0
        unrealized = (curr_p - trade.entry_price) * trade.quantity if (trade.entry_price and trade.quantity) else 0.0
        delta = (btc_price - p2b) if (btc_price is not None and p2b is not None) else None

        audit = BTC5MExitAudit(
            trade_id=trade.id,
            instance_id=self.instance_id,
            market_id=trade.market_id,
            event_type=event_type,
            timestamp=now,
            locked_predicted_side=trade.locked_predicted_side or ("YES" if trade.side == "BUY" else "NO"),
            current_live_prediction=features.get("predicted_side", "NONE"),
            btc_price=btc_price,
            p2b=p2b,
            delta=delta,
            momentum=features.get("short_momentum_1m", 0.0),
            probability=features.get("fair_prob_yes") if trade.side == "BUY" else (1.0 - (features.get("fair_prob_yes") or 0.5)),
            orderbook_imbalance=features.get("bid_ask_imbalance", 0.0),
            volatility=features.get("rolling_volatility", 0.0),
            remaining_time=time_remaining_sec,
            entry_price=trade.entry_price,
            current_price=curr_p,
            unrealized_pnl=unrealized,
            original_stop=trade.entry_stop_price or trade.stop_loss_price,
            hard_stop=trade.hard_stop_price,
            current_exit_decision=current_exit_decision,
            thesis_failure_score=thesis_failure_score,
            reason=reason,
            details_json=json.dumps(breakdown)
        )
        self.db.add(audit)
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"[BTC5M ExitManager] Audit record error: {e}")
        return audit
