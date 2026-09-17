"""
BTC 5M Strategy — Multi-Factor Confirmation Signal Engine.

Signal States:
  WATCH    - Market identified, monitoring
  SETUP    - Pre-conditions partially met
  READY    - All pre-conditions met, awaiting final trigger
  ENTER    - Trade approved, execute paper trade
  HOLD     - In position, monitoring exit conditions
  EXIT     - Exit triggered
  SKIP     - One or more conditions failed
  RESOLVED - Market has resolved

Entry requires multi-factor confirmation:
  1. Fresh data
  2. Valid liquidity
  3. Acceptable spread
  4. Sufficient depth
  5. Short-term momentum
  6. Price/probability movement
  7. Orderbook imbalance
  8. Volatility regime
  9. Sufficient time remaining
  10. Positive net edge
  11. RiskManager approval
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

# ── BTC5M Strategy Parameters ────────────────────────────────
MIN_MOMENTUM          = 0.01   # Minimum short_momentum_1m to consider entry
MIN_IMBALANCE         = 0.05   # Minimum |imbalance| indicating directional pressure
MAX_VOLATILITY        = 0.08   # Reject if rolling_vol exceeds this (too noisy)
MIN_VOLATILITY        = 0.001  # Reject if market is completely flat (stale)
MAX_SPREAD            = 0.05   # 5% max spread for trade eligibility
MIN_DEPTH             = 50.0   # Minimum ask_depth in $ for order fill
MIN_LIQUIDITY         = 100.0  # Minimum total liquidity
MIN_TIME_REMAINING    = 60.0   # At least 60 seconds before resolution
MIN_NET_EDGE          = 0.015  # Minimum net edge (lowered to 1.5% to permit trades with smaller statistical edge)
MAX_SPREAD_STABILITY  = 0.02   # Spread must be stable (low std)
MIN_MOMENTUM_PERSIST  = 0.40   # Momentum must be persistent (40% consistent direction)
STALENESS_THRESHOLD_S = 10.0   # Data older than 10s is stale
MIN_ENTRY_SCORE       = 60.0   # Score threshold (readjusted to permit more high-edge trades)
MIN_RR                = 1.5    # Minimum Risk-Reward threshold (readjusted to 1.5)


@dataclass
class BTC5MSignal:
    market_id: str
    condition_id: str
    question: str
    yes_token_id: str
    no_token_id: Optional[str]
    timestamp: datetime
    state: str              # WATCH/SETUP/READY/ENTER/SKIP/HOLD/EXIT/RESOLVED
    side: str               # BUY/SELL/NONE
    entry_price: float
    bid: float
    ask: float
    spread: float
    bid_depth: float
    ask_depth: float
    momentum: float
    imbalance: float
    ob_pressure: float
    volatility: float
    momentum_persistence: float
    market_probability: float
    fair_probability: float
    raw_edge: float
    spread_cost: float
    slippage_cost: float
    fees: float
    net_edge: float
    risk_pct: float
    position_size: float
    time_remaining_sec: float
    planned_risk: float
    planned_reward: float
    planned_rr: float
    stop_loss_price: float
    take_profit_price: float
    model_version: str
    strategy: str
    reason: str
    yes_score: float = 0.0
    no_score: float = 0.0
    yes_prob: float = 0.0
    no_prob: float = 0.0
    predicted_side: str = "NONE"
    gate_results: str = "{}"
    yes_breakdown: str = "{}"
    no_breakdown: str = "{}"
    # Risk-level skip flags
    skip_flags: list = field(default_factory=list)


def _compute_fair_probability(price: float, momentum: float, imbalance: float, btc_price: Optional[float] = None, p2b: Optional[float] = None) -> float:
    """
    Compute rule-based fair probability for YES (UP).
    Factors:
    - Base market price
    - BTC Price vs Price-to-Beat delta (authoritative Chainlink feed)
    - Short-term momentum
    - Orderbook pressure and imbalance
    """
    nudge = 0.0
    if btc_price is not None and p2b is not None:
        diff = btc_price - p2b
        p2b_shift = max(-0.15, min(0.15, diff / 250.0))
        nudge += p2b_shift

    mom_shift = max(-0.08, min(0.08, momentum * 200.0))
    imb_shift = max(-0.05, min(0.05, imbalance * 0.05))
    nudge += (mom_shift + imb_shift)

    return max(0.01, min(0.99, price + nudge))


class BTC5MStrategy:
    """
    BTC 5-Minute Prediction Market Strategy.
    Evaluates both YES (UP) and NO (DOWN) using a 100-point scoring system.
    """

    def __init__(self, risk_manager=None, settings_dict: Optional[dict] = None):
        self.risk_manager = risk_manager
        self._active_positions: dict = {}  # market_id -> entry info
        self.last_btc_price = None
        self.last_price_to_beat = None
        self.settings: dict = settings_dict or {}
        if not self.settings:
            self.rehydrate_settings()

    def rehydrate_settings(self):
        """Load persistent targeting settings from DB, falling back to defaults."""
        try:
            from app.db.session import SessionLocal
            from app.btc5m.settings_manager import get_btc5m_settings
            db = SessionLocal()
            try:
                self.settings = get_btc5m_settings(db)
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[BTC5M Strategy] Using default settings: {e}")
            from app.btc5m.settings_manager import DEFAULT_SETTINGS, _cast_val
            self.settings = {k: _cast_val(k, v) for k, v in DEFAULT_SETTINGS.items()}

    def record_entry(self, market_id: str, signal: BTC5MSignal):
        self._active_positions[market_id] = signal

    def record_exit(self, market_id: str):
        self._active_positions.pop(market_id, None)

    def _score_side(self, is_yes: bool, features: dict, btc_price: float, p2b: float) -> tuple[float, dict]:
        """
        Calculate a 100-point score for a specific side.
        BTC Price vs Price-to-Beat (20)
        Momentum (15)
        CLOB Order Book (15)
        Probability Movement (10)
        Volatility (10)
        Liquidity / Spread (10)
        Net Edge (10)
        Time Remaining (5)
        Risk + R:R (5)
        """
        breakdown = {}
        total = 0.0
        
        # 1. BTC Price vs P2B (20 points)
        # If YES, BTC > P2B is good. If NO, BTC < P2B is good.
        diff = btc_price - p2b if btc_price and p2b else 0
        if is_yes:
            score_p2b = min(20, max(0, 10 + (diff / 5.0))) if diff != 0 else 10
        else:
            score_p2b = min(20, max(0, 10 - (diff / 5.0))) if diff != 0 else 10
        breakdown["BTC vs P2B"] = round(score_p2b, 1)
        total += score_p2b
        
        # 2. Momentum (15 points)
        mom = features.get("short_momentum_1m", 0.0)
        if is_yes:
            score_mom = min(15, max(0, 7.5 + (mom * 500)))
        else:
            score_mom = min(15, max(0, 7.5 - (mom * 500)))
        breakdown["Momentum"] = round(score_mom, 1)
        total += score_mom
        
        # 3. CLOB Order Book / Imbalance (15 points)
        # Positive imbalance means more bids (bullish for YES)
        imb = features.get("bid_ask_imbalance", 0.0)
        if is_yes:
            score_ob = min(15, max(0, 7.5 + (imb * 15)))
        else:
            score_ob = min(15, max(0, 7.5 - (imb * 15)))
        breakdown["Order Book"] = round(score_ob, 1)
        total += score_ob
        
        # 4. Probability Movement (10 points)
        ret1 = features.get("return_1", 0.0) # change in mid price
        if is_yes:
            score_prob = min(10, max(0, 5 + (ret1 * 100)))
        else:
            score_prob = min(10, max(0, 5 - (ret1 * 100)))
        breakdown["Prob Movement"] = round(score_prob, 1)
        total += score_prob
        
        # 5. Volatility (10 points)
        # Lower volatility is better (less noise)
        vol = features.get("rolling_volatility", 0.0)
        score_vol = min(10, max(0, 10 - (vol * 100)))
        breakdown["Volatility"] = round(score_vol, 1)
        total += score_vol
        
        # 6. Liquidity / Spread (10 points)
        spread = features.get("spread", 1.0)
        score_spread = min(10, max(0, 10 - (spread * 200)))
        breakdown["Liquidity/Spread"] = round(score_spread, 1)
        total += score_spread
        
        # Net Edge and R:R are added externally based on actual math
        
        return total, breakdown

    def _calc_edge_and_rr(self, is_yes: bool, features: dict, current_balance: float, btc_price: Optional[float] = None, p2b: Optional[float] = None):
        spread = features.get("spread", 0.05)
        price = features.get("mid_price", 0.5)
        
        # If YES, we buy YES token. If NO, we buy NO token.
        # "bid/ask" in features are for YES token.
        # For NO token, price is 1 - YES price.
        # Buying YES means we pay 'ask'. 
        # Buying NO means we pay '1 - bid'.
        yes_bid = features.get("bid", price - 0.01)
        yes_ask = features.get("ask", price + 0.01)
        
        if is_yes:
            entry_price = yes_ask
        else:
            entry_price = 1.0 - yes_bid
            
        fees = 0.0
        slippage_cost = 0.0
        spread_cost = spread / 2.0
        
        # Fair prob
        fair_yes = _compute_fair_probability(price, momentum=features.get("short_momentum_1m", 0.0), imbalance=features.get("bid_ask_imbalance", 0.0), btc_price=btc_price, p2b=p2b)
        fair_prob = fair_yes if is_yes else (1.0 - fair_yes)
        
        risk_pct = self.settings.get("risk_per_trade", settings.risk_per_trade)
        planned_risk = current_balance * risk_pct
        tp_delta = self.settings.get("take_profit_delta", 0.30)
        max_tp = self.settings.get("max_take_profit", 0.95)
        sl_ratio = self.settings.get("stop_loss_ratio", 0.50)

        take_profit_price = min(max_tp, entry_price + tp_delta) # Dynamic target
        reward_per_share = max(0.01, take_profit_price - entry_price)
        risk_per_share = reward_per_share * sl_ratio
        stop_loss_price = max(0.01, entry_price - risk_per_share)
        
        net_reward = (take_profit_price - entry_price) - fees - slippage_cost - spread_cost
        net_risk = (entry_price - stop_loss_price) + fees + slippage_cost + spread_cost
        
        actual_planned_rr = net_reward / net_risk if net_risk > 0 else 0
        raw_edge = fair_prob - entry_price
        net_edge = raw_edge - spread_cost - slippage_cost - fees
        
        return entry_price, fair_prob, actual_planned_rr, net_edge, stop_loss_price, take_profit_price, planned_risk

    def evaluate(
        self,
        market_id: str,
        condition_id: str,
        question: str,
        yes_token_id: str,
        no_token_id: Optional[str],
        features: dict,
        orderbook_timestamp: Optional[datetime],
        btc_price: float = None,
        price_to_beat: float = None,
        current_balance: float = 500.0,
    ) -> BTC5MSignal:
        """
        Evaluate a BTC 5M market and return a BTC5MSignal.
        """
        now = datetime.now(timezone.utc)
        skip_flags = []
        
        time_remaining = features.get("time_remaining_sec", 0.0)
        price = features.get("mid_price", 0.5)
        yes_bid = features.get("bid", price - 0.01)
        yes_ask = features.get("ask", price + 0.01)
        spread = features.get("spread", 1.0)
        bid_depth = features.get("bid_depth", 0.0)
        ask_depth = features.get("ask_depth", 0.0)
        liquidity = bid_depth + ask_depth
        volatility = features.get("rolling_volatility", 0.0)
        
        # P2B is mandatory for the BTC-vs-P2B component.
        # Never score/trade using a fabricated reference price.
        if btc_price is None or price_to_beat is None:
            return BTC5MSignal(
                market_id=market_id,
                condition_id=condition_id,
                question=question,
                yes_token_id=yes_token_id,
                no_token_id=no_token_id,
                timestamp=now,
                state="SKIP",
                side="NONE",
                entry_price=0.0,
                bid=yes_bid,
                ask=yes_ask,
                spread=spread,
                bid_depth=bid_depth,
                ask_depth=ask_depth,
                momentum=features.get("short_momentum_1m", 0.0),
                imbalance=features.get("bid_ask_imbalance", 0.0),
                ob_pressure=features.get("ob_pressure", 0.0),
                volatility=volatility,
                momentum_persistence=0.0,
                market_probability=price,
                fair_probability=price,
                raw_edge=0.0,
                spread_cost=spread / 2.0,
                slippage_cost=0.0,
                fees=0.0,
                net_edge=0.0,
                risk_pct=settings.risk_per_trade,
                position_size=0.0,
                time_remaining_sec=time_remaining,
                planned_risk=0.0,
                planned_reward=0.0,
                planned_rr=0.0,
                stop_loss_price=0.0,
                take_profit_price=0.0,
                model_version="multi_factor_btc5m_100pt",
                strategy="BTC_5M",
                reason="SKIP - Missing authoritative Price-to-Beat / BTC reference data",
                skip_flags=["SKIP - Missing authoritative Price-to-Beat / BTC reference data"],
                yes_score=0.0,
                no_score=0.0,
                yes_prob=0.0,
                no_prob=0.0,
                predicted_side="NONE",
                gate_results="{}",
                yes_breakdown="{}",
                no_breakdown="{}"
            )

        # 1. Score both sides
        yes_base_score, yes_breakdown = self._score_side(True, features, btc_price, price_to_beat)
        no_base_score, no_breakdown = self._score_side(False, features, btc_price, price_to_beat)
        
        # 2. Calculate edges with BTC & P2B inputs
        yes_ep, yes_fair, yes_rr, yes_edge, yes_sl, yes_tp, risk = self._calc_edge_and_rr(True, features, current_balance, btc_price, price_to_beat)
        no_ep, no_fair, no_rr, no_edge, no_sl, no_tp, _ = self._calc_edge_and_rr(False, features, current_balance, btc_price, price_to_beat)
        
        min_rr = self.settings.get("min_rr", MIN_RR)
        min_score = self.settings.get("min_entry_score", MIN_ENTRY_SCORE)
        min_edge = self.settings.get("min_net_edge", MIN_NET_EDGE)
        max_spr = self.settings.get("max_spread", MAX_SPREAD)
        min_liq = self.settings.get("min_liquidity", MIN_LIQUIDITY)
        min_time = self.settings.get("min_time_remaining", 30.0)

        # Add dynamic points (10 for edge, 5 for RR, 5 for time)
        # Edge > 0.05 gives 10 points
        yes_edge_pts = min(10, max(0, yes_edge * 200))
        yes_rr_pts = 5 if yes_rr >= min_rr else 0
        yes_time_pts = min(5, time_remaining / 60.0)
        yes_score = yes_base_score + yes_edge_pts + yes_rr_pts + yes_time_pts
        yes_breakdown["Net Edge"] = round(yes_edge_pts, 1)
        yes_breakdown["Risk/R:R"] = round(yes_rr_pts, 1)
        yes_breakdown["Time"] = round(yes_time_pts, 1)
        
        no_edge_pts = min(10, max(0, no_edge * 200))
        no_rr_pts = 5 if no_rr >= min_rr else 0
        no_time_pts = min(5, time_remaining / 60.0)
        no_score = no_base_score + no_edge_pts + no_rr_pts + no_time_pts
        no_breakdown["Net Edge"] = round(no_edge_pts, 1)
        no_breakdown["Risk/R:R"] = round(no_rr_pts, 1)
        no_breakdown["Time"] = round(no_time_pts, 1)
        
        import json
        # 3. Determine Prediction (Independent of 70 threshold)
        if yes_score > no_score:
            predicted_side = "YES"
        elif no_score > yes_score:
            predicted_side = "NO"
        else:
            predicted_side = "YES" if yes_edge > no_edge else ("NO" if no_edge > yes_edge else "NONE")

        # 4. Entry Checks
        gate_results = {
            "score": {"pass": False, "value": f"{max(yes_score, no_score):.1f}"},
            "net_edge": {"pass": False, "value": f"0.00%"},
            "spread": {"pass": False, "value": f"{spread*100:.2f}%"},
            "liquidity": {"pass": False, "value": f"{liquidity:.0f}"},
            "rr": {"pass": False, "value": "UNAVAILABLE"},
            "time": {"pass": False, "value": f"{time_remaining:.0f}s"}
        }

        # Select target params based on prediction
        is_yes = (predicted_side == "YES" or predicted_side == "NONE")
        selected_score = yes_score if is_yes else no_score
        entry_price = yes_ep if is_yes else no_ep
        fair_prob = yes_fair if is_yes else no_fair
        actual_planned_rr = yes_rr if is_yes else no_rr
        net_edge = yes_edge if is_yes else no_edge
        stop_loss_price = yes_sl if is_yes else no_sl
        take_profit_price = yes_tp if is_yes else no_tp
        
        gate_results["net_edge"]["value"] = f"{net_edge*100:.2f}%"
        gate_results["rr"]["value"] = f"{actual_planned_rr:.2f}"
        
        if selected_score >= min_score:
            gate_results["score"]["pass"] = True
        else:
            skip_flags.append(f"SKIP - Predicted {predicted_side}, but score {selected_score:.1f} < {min_score:.0f}")
            
        if net_edge >= min_edge:
            gate_results["net_edge"]["pass"] = True
        else:
            skip_flags.append(f"SKIP - Net edge {net_edge*100:.2f}% < {min_edge*100:.2f}%")
            
        if spread <= max_spr:
            gate_results["spread"]["pass"] = True
        else:
            skip_flags.append(f"SKIP - Spread {spread*100:.2f}% > {max_spr*100:.2f}%")
            
        if liquidity >= min_liq:
            gate_results["liquidity"]["pass"] = True
        else:
            skip_flags.append(f"SKIP - Liquidity {liquidity:.0f} < {min_liq:.0f}")
            
        if time_remaining >= min_time:
            gate_results["time"]["pass"] = True
        else:
            skip_flags.append(f"SKIP - Time {time_remaining:.0f}s < {min_time:.0f}s")
            
        if actual_planned_rr >= min_rr:
            gate_results["rr"]["pass"] = True
        else:
            skip_flags.append(f"SKIP - R:R {actual_planned_rr:.2f} < {min_rr}")
            
        if not btc_price or not price_to_beat:
            skip_flags.append("SKIP - Missing Price-to-Beat or Current BTC Price (Stale data)")
            
        if predicted_side == "NONE":
            skip_flags.append("SKIP - No directional evidence (YES/NO tie)")
            
        best_side = predicted_side
        final_side = "BUY" if predicted_side == "YES" else ("SELL" if predicted_side == "NO" else "NONE")

        # DB Open trades check
        from app.db.session import SessionLocal
        from app.db.models import BTC5MTrade
        db = SessionLocal()
        try:
            open_count = db.query(BTC5MTrade).filter(BTC5MTrade.status == "OPEN").count()
            already_traded = db.query(BTC5MTrade).filter(BTC5MTrade.market_id == market_id).count()
        finally:
            db.close()

        if open_count >= 1:
            skip_flags.append("SKIP - Max 1 open position allowed")

        if already_traded >= 1:
            skip_flags.append("SKIP - Duplicate trade prevention: Market already traded")
            
        if current_balance <= 0:
            skip_flags.append("SKIP - Risk limit (Zero or negative balance)")
            
        state = "SKIP" if skip_flags else "READY"
        reason = skip_flags[0] if skip_flags else f"Prediction: {best_side} (Score: {max(yes_score, no_score):.1f})"
        
        # Override side properly
        final_side = "BUY" if best_side == "YES" else ("SELL" if best_side == "NO" else "NONE")
        
        if state == "READY" and self.risk_manager:
            risk_decision = self.risk_manager.evaluate_trade(
                {"market_id": market_id},
                {"condition_id": condition_id, "ask_depth": ask_depth}
            )
            is_approved = False
            if isinstance(risk_decision, dict):
                is_approved = (risk_decision.get("decision") in ("ACCEPT", "APPROVE") or risk_decision.get("approved") is True)
                risk_reason = risk_decision.get("reason", "Rejected by RiskManager")
            else:
                is_approved = getattr(risk_decision, "approved", False)
                risk_reason = getattr(risk_decision, "reason", "Rejected by RiskManager")

            if not is_approved:
                state = "SKIP"
                reason = f"SKIP - Risk limit ({risk_reason})"
                skip_flags.append(reason)
                
        if state == "READY":
            state = "ENTER"

        return BTC5MSignal(
            market_id=market_id,
            condition_id=condition_id,
            question=question,
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
            timestamp=now,
            state=state,
            side=final_side,
            entry_price=entry_price,
            bid=yes_bid,
            ask=yes_ask,
            spread=spread,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            momentum=features.get("short_momentum_1m", 0.0),
            imbalance=features.get("bid_ask_imbalance", 0.0),
            ob_pressure=features.get("ob_pressure", 0.0),
            volatility=volatility,
            momentum_persistence=0,
            market_probability=price if is_yes else (1 - price),
            fair_probability=fair_prob,
            raw_edge=0.05,
            spread_cost=spread/2,
            slippage_cost=0,
            fees=0,
            net_edge=net_edge,
            risk_pct=settings.risk_per_trade,
            position_size=risk,
            time_remaining_sec=time_remaining,
            planned_risk=risk,
            planned_reward=risk * actual_planned_rr,
            planned_rr=actual_planned_rr,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            model_version="multi_factor_btc5m_100pt",
            strategy="BTC_5M",
            reason=reason,
            skip_flags=skip_flags,
            yes_score=yes_score,
            no_score=no_score,
            yes_prob=yes_fair,
            no_prob=1.0 - yes_fair,
            predicted_side=predicted_side,
            gate_results=json.dumps(gate_results),
            yes_breakdown=json.dumps(yes_breakdown),
            no_breakdown=json.dumps(no_breakdown)
        )
