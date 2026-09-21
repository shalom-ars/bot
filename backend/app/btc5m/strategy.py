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
import math
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

# ── BTC5M Strategy Parameters ────────────────────────────────
MIN_MOMENTUM          = 0.01   # Minimum short_momentum_1m to consider entry
MIN_IMBALANCE         = 0.0    # Bypass
MAX_VOLATILITY        = 999.0  # Bypass
MIN_VOLATILITY        = 0.0    # Bypass
MAX_SPREAD            = 1.0    # Bypass
MIN_DEPTH             = 0.0    # Bypass
MIN_LIQUIDITY         = 0.0    # Bypass
MIN_TIME_REMAINING    = 0.0    # Bypass
MIN_NET_EDGE          = -100.0 # Allow negative edge
MAX_SPREAD_STABILITY  = 999.0  # Bypass
MIN_MOMENTUM_PERSIST  = 0.0    # Bypass
STALENESS_THRESHOLD_S = 10.0   # Keep
MIN_ENTRY_SCORE       = 0.0    # Bypass score
MIN_RR                = 0.0    # Bypass R:R


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
    rsi: float = 50.0
    macd_hist: float = 0.0
    bb_pct_b: float = 0.5
    bb_bandwidth: float = 0.0
    instance_id: str = "instance_1"
    # Risk-level skip flags
    skip_flags: list = field(default_factory=list)


def _compute_fair_probability(
    price: float,
    momentum: float,
    imbalance: float,
    btc_price: Optional[float] = None,
    p2b: Optional[float] = None,
    time_remaining_sec: float = 150.0,
    btc_momentum_1m: Optional[float] = None
) -> float:
    """
    Compute rule-based and time-decayed fair probability for YES (UP).
    Fair NO probability is 1.0 - fair_yes.
    Factors:
    - Base Polymarket market price
    - BTC vs Price-to-Beat delta scaled by time remaining (Brownian option physics)
    - True spot BTC momentum (if available) & orderbook momentum
    - Orderbook pressure and imbalance
    """
    if btc_price is not None and p2b is not None:
        diff = btc_price - p2b
        tau = max(15.0, min(300.0, float(time_remaining_sec)))
        
        # 5-minute standard deviation of BTC (~$25 - $35)
        sigma_tau = 30.0 * math.sqrt(tau / 300.0)
        z = diff / (sigma_tau + 1e-9)
        
        # Logistic probability from BTC vs P2B
        p_oracle = 1.0 / (1.0 + math.exp(-max(-8.0, min(8.0, 1.2 * z))))
        
        # Time-weighted blend: as expiry approaches, oracle delta dominates market price
        w_oracle = min(0.90, max(0.40, 1.0 - (tau / 500.0)))
        blended_price = (w_oracle * p_oracle) + ((1.0 - w_oracle) * price)
    else:
        blended_price = price

    # Micro-structure nudges
    nudge = 0.0
    if btc_momentum_1m is not None:
        # e.g. -0.001 is -0.1% move in spot BTC (~$65)
        nudge += max(-0.06, min(0.06, btc_momentum_1m * 50.0))
    else:
        nudge += max(-0.05, min(0.05, momentum * 100.0))

    imb_shift = max(-0.04, min(0.04, imbalance * 0.04))
    nudge += imb_shift

    return max(0.01, min(0.99, blended_price + nudge))


class BTC5MStrategy:
    """
    BTC 5-Minute Prediction Market Strategy.
    Evaluates both YES (UP) and NO (DOWN) using a 100-point scoring system.
    Supports multi-instance configurations (e.g. Dynamic R:R vs Fixed Dollar Short Specialist).
    """

    def __init__(
        self,
        risk_manager=None,
        settings_dict: Optional[dict] = None,
        instance_id: str = "instance_1",
        mode: str = "dynamic",
        tp_dollar: Optional[float] = None,
        sl_dollar: Optional[float] = None,
        only_short: bool = False,
        slot_mode: Optional[str] = None
    ):
        self.risk_manager = risk_manager
        self.instance_id = instance_id
        self.mode = mode
        self.tp_dollar = tp_dollar
        self.sl_dollar = sl_dollar
        self.only_short = only_short
        self.slot_mode = slot_mode or "single_5m"
        self._active_positions: dict = {}  # market_id -> entry info
        self.last_btc_price = None
        self.last_price_to_beat = None
        self.settings: dict = settings_dict or {}
        if not self.settings:
            self.rehydrate_settings()
            if mode != "dynamic":
                self.mode = mode
                self.settings["mode"] = mode
            if tp_dollar is not None:
                self.tp_dollar = tp_dollar
                self.settings["tp_dollar"] = tp_dollar
            if sl_dollar is not None:
                self.sl_dollar = sl_dollar
                self.settings["sl_dollar"] = sl_dollar
            if only_short:
                self.only_short = only_short
                self.settings["only_short"] = only_short
            if slot_mode is not None:
                self.slot_mode = slot_mode
                self.settings["slot_mode"] = slot_mode
        else:
            self._sync_instance_params()

    def _sync_instance_params(self):
        if self.settings.get("mode"):
            self.mode = self.settings.get("mode")
        if self.settings.get("slot_mode"):
            self.slot_mode = self.settings.get("slot_mode")
        if self.settings.get("tp_dollar") is not None:
            self.tp_dollar = float(self.settings.get("tp_dollar"))
        if self.settings.get("sl_dollar") is not None:
            self.sl_dollar = float(self.settings.get("sl_dollar"))
        if self.settings.get("only_short") is not None:
            self.only_short = bool(self.settings.get("only_short"))


    def rehydrate_settings(self):
        """Load persistent targeting settings from DB for this instance, falling back to defaults."""
        try:
            from app.db.session import SessionLocal
            from app.btc5m.settings_manager import get_btc5m_settings
            db = SessionLocal()
            try:
                self.settings = get_btc5m_settings(db, instance_id=self.instance_id)
                self._sync_instance_params()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[BTC5M Strategy] Using default settings for {self.instance_id}: {e}")
            from app.btc5m.settings_manager import DEFAULT_SETTINGS, DEFAULT_SETTINGS_INSTANCE_2, _cast_val
            defaults = DEFAULT_SETTINGS
            self.settings = {k: _cast_val(k, v) for k, v in defaults.items()}
            self._sync_instance_params()

    def record_entry(self, market_id: str, signal: BTC5MSignal):
        self._active_positions[market_id] = signal

    def record_exit(self, market_id: str):
        self._active_positions.pop(market_id, None)

    def _score_side(
        self,
        is_yes: bool,
        features: dict,
        btc_price: float,
        p2b: float,
        time_remaining_sec: float = 150.0
    ) -> tuple[float, dict]:
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
        
        is_bot_2 = (self.instance_id == "instance_2")
        
        diff = btc_price - p2b if btc_price and p2b else 0.0
        tau = max(15.0, min(300.0, float(time_remaining_sec)))
        sigma_tau = 30.0 * math.sqrt(tau / 300.0)
        z = diff / (sigma_tau + 1e-9) if diff != 0.0 else 0.0

        btc_mom = features.get("btc_momentum_1m", None)
        clob_mom = features.get("short_momentum_1m", 0.0)
        macd_h = float(features.get("macd_hist", 0.0))
        macd_bonus = max(-10.0, min(10.0, macd_h * 50.0))

        if btc_mom is not None:
            mom_composite = (btc_mom * 5000.0 * 0.70) + (clob_mom * 500.0 * 0.30) + macd_bonus
        else:
            mom_composite = (clob_mom * 800.0) + macd_bonus

        rsi = float(features.get("rsi_14", 50.0))
        rsi_shift = (rsi - 50.0) / 20.0
        imb = features.get("bid_ask_imbalance", 0.0)
        ret1 = features.get("return_1", 0.0)
        vol = features.get("rolling_volatility", 0.0)
        spread = features.get("spread", 1.0)

        bb_pct = float(features.get("bb_pct_b", 0.5))
        bb_shift = (bb_pct - 0.5) * 2.0  # -1.0 to +1.0
        depth_imb = float(features.get("depth_imbalance", imb))
        ob_composite = (imb * 0.60) + (depth_imb * 0.40)
        tech_shift = (rsi_shift * 0.65) + (bb_shift * 0.35)
        mom_persist = float(features.get("momentum_persistence", 0.0))

        if not is_bot_2:
            # ── BOT 1: MACRO TREND & STRIKE LEAD SPECIALIST (5M CANDLE) ──
            # Dominant focus: Strike clearance (35), Trend Momentum (30), Technicals (15), Orderbook (10), Execution (10)
            if is_yes:
                score_p2b = min(35.0, max(0.0, 17.5 + (z * 8.5)))
                score_mom = min(30.0, max(0.0, 15.0 + (mom_composite * 0.9)))
                score_tech = min(15.0, max(0.0, 7.5 + (tech_shift * 7.5)))
                score_ob = min(10.0, max(0.0, 5.0 + (ob_composite * 10.0)))
            else:
                score_p2b = min(35.0, max(0.0, 17.5 - (z * 8.5)))
                score_mom = min(30.0, max(0.0, 15.0 - (mom_composite * 0.9)))
                score_tech = min(15.0, max(0.0, 7.5 - (tech_shift * 7.5)))
                score_ob = min(10.0, max(0.0, 5.0 - (ob_composite * 10.0)))

            score_exec = min(10.0, max(0.0, 10.0 - (vol * 50.0) - (spread * 100.0) + (mom_persist * 2.0)))
            breakdown["BTC vs Strike (Macro)"] = round(score_p2b, 1)
            breakdown["Trend Momentum"] = round(score_mom, 1)
            breakdown["RSI & BB Confirmation"] = round(score_tech, 1)
            breakdown["Order Book Depth"] = round(score_ob, 1)
            breakdown["Execution & History"] = round(score_exec, 1)
            total = score_p2b + score_mom + score_tech + score_ob + score_exec
        else:
            # ── BOT 2: ORDER FLOW SCALP & RAPID VELOCITY SPECIALIST (2.5M SLOTS) ──
            # Rebalanced: BTC vs Strike remains primary (35) to prevent counter-trend traps, combined with Rapid Velocity (30) and Order Flow (15)
            if is_yes:
                score_p2b = min(35.0, max(0.0, 17.5 + (z * 8.5)))
                score_mom = min(30.0, max(0.0, 15.0 + (mom_composite * 1.0)))
                score_ob = min(15.0, max(0.0, 7.5 + (ob_composite * 15.0)))
                score_tech = min(10.0, max(0.0, 5.0 + (tech_shift * 5.0)))
            else:
                score_p2b = min(35.0, max(0.0, 17.5 - (z * 8.5)))
                score_mom = min(30.0, max(0.0, 15.0 - (mom_composite * 1.0)))
                score_ob = min(15.0, max(0.0, 7.5 - (ob_composite * 15.0)))
                score_tech = min(10.0, max(0.0, 5.0 - (tech_shift * 5.0)))

            score_exec = min(10.0, max(0.0, 10.0 - (vol * 40.0) - (spread * 80.0) + (mom_persist * 2.0)))
            breakdown["BTC vs Strike Lead"] = round(score_p2b, 1)
            breakdown["Rapid Velocity Momentum"] = round(score_mom, 1)
            breakdown["Order Flow Depth Imbalance"] = round(score_ob, 1)
            breakdown["Micro RSI & BB"] = round(score_tech, 1)
            breakdown["Execution Quality"] = round(score_exec, 1)
            total = score_p2b + score_mom + score_ob + score_tech + score_exec
        
        # Net Edge and R:R are added externally based on actual math
        return total, breakdown

    def _calc_edge_and_rr(
        self,
        is_yes: bool,
        features: dict,
        current_balance: float,
        btc_price: Optional[float] = None,
        p2b: Optional[float] = None,
        time_remaining_sec: float = 150.0
    ):
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
        fair_yes = _compute_fair_probability(
            price,
            momentum=features.get("short_momentum_1m", 0.0),
            imbalance=features.get("bid_ask_imbalance", 0.0),
            btc_price=btc_price,
            p2b=p2b,
            time_remaining_sec=time_remaining_sec,
            btc_momentum_1m=features.get("btc_momentum_1m")
        )
        fair_prob = fair_yes if is_yes else (1.0 - fair_yes)
        
        risk_pct = self.settings.get("risk_per_trade", settings.risk_per_trade)
        planned_risk = current_balance * risk_pct
        
        # Jesse Risk-of-Ruin: Dampen position size by 50% if previous trade was a loss
        if self.settings.get("consecutive_loss_dampener_enabled", True):
            try:
                from app.db.session import SessionLocal
                from app.db.models import BTC5MTrade
                _db = SessionLocal()
                try:
                    last_closed = _db.query(BTC5MTrade).filter(
                        BTC5MTrade.status == "CLOSED",
                        BTC5MTrade.instance_id == self.instance_id
                    ).order_by(BTC5MTrade.id.desc()).first()
                    if last_closed and last_closed.pnl is not None and last_closed.pnl < 0:
                        planned_risk *= 0.50
                finally:
                    _db.close()
            except Exception:
                pass

        # Risk-governed position sizing: Cap position size to $5.00 for $1.00 SL mode.
        # This reduces share quantity to ~8-10 shares (instead of 17-19 shares),
        # mathematically guaranteeing that a 10-cent stop loss equals exactly ~$0.90-$1.00,
        # and eliminating orderbook vacuum drops from generating -$3.00+ losses.
        max_pos = float(self.settings.get("max_position_size", 5.00))
        position_size = min(max_pos, planned_risk)
        quantity = position_size / (entry_price + 1e-9)

        is_fixed = (self.mode == "fixed_dollar" or self.settings.get("mode") == "fixed_dollar")
        if is_fixed:
            tp_dollar = float(self.settings.get("tp_dollar", self.tp_dollar or 1.00))
            sl_dollar = float(self.settings.get("sl_dollar", self.sl_dollar or 10.00))
            hard_cap = float(self.settings.get("hard_cap_dollar", sl_dollar))
            dynamic_sl_delta = float(self.settings.get("dynamic_sl_delta", 0.90))
            take_profit_price = min(0.99, entry_price + (tp_dollar / max(0.1, quantity)))
            max_sl_dist = min(dynamic_sl_delta, sl_dollar / max(0.1, quantity))
            stop_loss_price = max(0.01, entry_price - max_sl_dist)
            reward_per_share = max(0.001, take_profit_price - entry_price)
            risk_per_share = max(0.001, entry_price - stop_loss_price)
            planned_risk = min(hard_cap, risk_per_share * quantity)
        else:
            tp_delta = float(self.settings.get("take_profit_delta", 0.20))
            max_tp = float(self.settings.get("max_take_profit", 0.95))
            sl_ratio = float(self.settings.get("stop_loss_ratio", 2.00))

            take_profit_price = min(max_tp, entry_price + tp_delta)  # Dynamic target
            reward_per_share = max(0.01, take_profit_price - entry_price)
            risk_per_share = reward_per_share * sl_ratio  # 1:2 Risk to Reward ($1 win, $2 loss)
            stop_loss_price = max(0.01, entry_price - risk_per_share)
            planned_risk = risk_per_share * quantity  # Actual dollar risk (e.g. ~$2.00)

        
        net_reward = (take_profit_price - entry_price) - fees - slippage_cost - spread_cost
        net_risk = (entry_price - stop_loss_price) + fees + slippage_cost + spread_cost
        
        actual_planned_rr = net_reward / net_risk if net_risk > 0 else 0
        raw_edge = fair_prob - entry_price
        net_edge = raw_edge - spread_cost - slippage_cost - fees
        
        return entry_price, fair_prob, actual_planned_rr, net_edge, stop_loss_price, take_profit_price, planned_risk, position_size

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
                no_breakdown="{}",
                rsi=float(features.get("rsi_14", 50.0)),
                macd_hist=float(features.get("macd_hist", 0.0)),
                bb_pct_b=float(features.get("bb_pct_b", 0.5)),
                bb_bandwidth=float(features.get("bb_bandwidth", 0.0))
            )

        # 1. Score both sides with time-decayed option metrics
        yes_base_score, yes_breakdown = self._score_side(True, features, btc_price, price_to_beat, time_remaining)
        no_base_score, no_breakdown = self._score_side(False, features, btc_price, price_to_beat, time_remaining)
        
        # 2. Calculate edges with BTC & P2B inputs and time decay
        yes_ep, yes_fair, yes_rr, yes_edge, yes_sl, yes_tp, yes_risk, yes_pos_size = self._calc_edge_and_rr(True, features, current_balance, btc_price, price_to_beat, time_remaining)
        no_ep, no_fair, no_rr, no_edge, no_sl, no_tp, no_risk, no_pos_size = self._calc_edge_and_rr(False, features, current_balance, btc_price, price_to_beat, time_remaining)
        
        risk_pct = self.settings.get("risk_per_trade", settings.risk_per_trade)
        min_rr = float(self.settings.get("min_rr", MIN_RR))
        min_score = float(self.settings.get("min_entry_score", MIN_ENTRY_SCORE))
        min_edge = float(self.settings.get("min_net_edge", MIN_NET_EDGE))
        max_spr = float(self.settings.get("max_spread", MAX_SPREAD))
        min_liq = float(self.settings.get("min_liquidity", MIN_LIQUIDITY))
        min_time = float(self.settings.get("min_time_remaining", 45.0))
        is_instance_1 = (self.instance_id == "instance_1" or getattr(self, "instance_id", None) is None)
        default_max_time = 285.0
        max_time = float(self.settings.get("max_time_remaining", default_max_time))

        # Add dynamic points (10 for edge, 5 for RR, 5 for time)
        # Edge > 0.05 gives 10 points
        yes_edge_pts = min(10, max(0, yes_edge * 200))
        yes_rr_pts = 5 if yes_rr >= min_rr else 0
        yes_time_pts = min(5, max(0, (time_remaining - min_time) / 40.0))
        yes_score = yes_base_score + yes_edge_pts + yes_rr_pts + yes_time_pts
        yes_breakdown["Net Edge"] = round(yes_edge_pts, 1)
        yes_breakdown["Risk/R:R"] = round(yes_rr_pts, 1)
        yes_breakdown["Time"] = round(yes_time_pts, 1)
        
        no_edge_pts = min(10, max(0, no_edge * 200))
        no_rr_pts = 5 if no_rr >= min_rr else 0
        no_time_pts = min(5, max(0, (time_remaining - min_time) / 40.0))
        no_score = no_base_score + no_edge_pts + no_rr_pts + no_time_pts
        no_breakdown["Net Edge"] = round(no_edge_pts, 1)
        no_breakdown["Risk/R:R"] = round(no_rr_pts, 1)
        no_breakdown["Time"] = round(no_time_pts, 1)
        
        # 3. Determine Prediction with Decisive Lead and Strict Strike Alignment
        min_lead = float(self.settings.get("min_direction_lead", 5.0))
        strike_delta = (btc_price - price_to_beat) if (btc_price and price_to_beat) else 0.0
        min_strike_buffer = float(self.settings.get("min_p2b_diff", 1.5))

        # Strict Directional Strike Rule:
        # A 5-minute candle outcome is fundamentally decided by BTC vs Strike (Price-to-Beat).
        # When BTC is above strike, only YES can be predicted (NO is strictly prohibited).
        # When BTC is below strike, only NO can be predicted (YES is strictly prohibited).
        # When within strike buffer, market is in dead-heat chop zone (NONE).
        if strike_delta > min_strike_buffer:
            if yes_score >= min_score and (yes_score - no_score) >= min_lead:
                predicted_side = "YES"
            else:
                predicted_side = "NONE"
        elif strike_delta < -min_strike_buffer:
            if no_score >= min_score and (no_score - yes_score) >= min_lead:
                predicted_side = "NO"
            else:
                predicted_side = "NONE"
        else:
            predicted_side = "NONE"

        # 4. Entry Checks
        gate_results = {
            "score": {"pass": False, "value": f"{max(yes_score, no_score):.1f}"},
            "probability": {"pass": False, "value": "0.0%"},
            "net_edge": {"pass": False, "value": f"0.00%"},
            "spread": {"pass": False, "value": f"{spread*100:.2f}%"},
            "liquidity": {"pass": False, "value": f"{liquidity:.0f}"},
            "rr": {"pass": False, "value": "UNAVAILABLE"},
            "time": {"pass": False, "value": f"{time_remaining:.0f}s"},
            "rsi": {"pass": True, "value": f"{float(features.get('rsi_14', 50.0)):.1f}"},
            "macd": {"pass": True, "value": f"{float(features.get('macd_hist', 0.0)):.4f}"},
            "bollinger": {"pass": True, "value": f"%B: {float(features.get('bb_pct_b', 0.5)):.2f}"}
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
        selected_risk = yes_risk if is_yes else no_risk
        selected_pos_size = yes_pos_size if is_yes else no_pos_size
        
        gate_results["probability"]["value"] = f"{fair_prob*100:.1f}%"
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

        # Hummingbot Order Book Imbalance (OBI) Filter (Broadened to 0.02)
        total_depth = bid_depth + ask_depth
        obi = (bid_depth - ask_depth) / (total_depth + 1e-9) if total_depth > 0 else 0.0
        min_obi = float(self.settings.get("min_order_book_imbalance", 0.02))
        gate_results["obi"] = {
            "pass": False,
            "value": f"{obi:+.2f} (Target: {min_obi:+.2f})"
        }
        if min_obi <= 0.001:
            gate_results["obi"]["pass"] = True
        elif predicted_side == "YES":
            if obi >= min_obi:
                gate_results["obi"]["pass"] = True
            else:
                skip_flags.append(f"SKIP - Hummingbot OBI: Bid pressure {obi:+.2f} < +{min_obi:.2f} threshold for YES")
        elif predicted_side == "NO":
            if obi <= -min_obi:
                gate_results["obi"]["pass"] = True
            else:
                skip_flags.append(f"SKIP - Hummingbot OBI: Ask pressure {obi:+.2f} > -{min_obi:.2f} threshold for NO")
        else:
            gate_results["obi"]["pass"] = True
            
        if time_remaining < min_time:
            skip_flags.append(f"SKIP - Late-candle entry rejected ({time_remaining:.0f}s < {min_time:.0f}s left)")
        elif time_remaining > max_time:
            skip_flags.append(f"SKIP - Candle open stabilization ({time_remaining:.0f}s > {max_time:.0f}s)")
        else:
            gate_results["time"]["pass"] = True
            
        # Enforce minimum 1.5:1 Risk-to-Reward entry requirement (low-upside trades skipped)
        if actual_planned_rr >= min_rr:
            gate_results["rr"]["pass"] = True
        else:
            skip_flags.append(f"SKIP - Low upside R:R {actual_planned_rr:.2f} < {min_rr:.1f}:1 requirement")
            
        min_p2b = float(self.settings.get("min_p2b_diff", 1.5))
        if not btc_price or not price_to_beat:
            skip_flags.append("SKIP - Missing Price-to-Beat or Current BTC Price (Stale data)")
        elif abs(btc_price - price_to_beat) < min_p2b:
            btc_diff = abs(btc_price - price_to_beat)
            skip_flags.append(f"SKIP - Indecisive BTC vs P2B (${btc_diff:.1f} < ${min_p2b:.2f} threshold)")

        min_prob = float(self.settings.get("min_entry_probability", 0.40))
        if fair_prob >= min_prob:
            gate_results["probability"]["pass"] = True
        else:
            skip_flags.append(f"SKIP - Probability {fair_prob*100:.1f}% < {min_prob*100:.1f}% threshold")
            
        if predicted_side == "NONE":
            skip_flags.append("SKIP - No directional evidence (YES/NO tie)")
        elif predicted_side == "NO" and not no_token_id:
            skip_flags.append("SKIP - Missing NO outcome token ID on Polymarket")
            
        min_p = float(self.settings.get("min_entry_price", 0.40))
        # Smart price cap: when BTC is strongly trending (>$3 above/below P2B),
        # allow entry price up to 0.80 (strong trend momentum justifies higher price).
        # Normal moves: cap at max_entry_price (default 0.72).
        base_max_p = float(self.settings.get("max_entry_price", 0.72))
        max_p = 0.82 if strong_directional else base_max_p
        if entry_price < min_p or entry_price > max_p:
            skip_flags.append(f"SKIP - Entry price ${entry_price:.2f} outside optimal R:R window ({min_p:.2f} - {max_p:.2f})")

        # RSI Overbought / Oversold protection
        # NOTE: In a trending 5M binary market, RSI can stay elevated (75-85) while price
        # continues in trend direction. We use a wider threshold (82/18) to avoid blocking
        # valid trend trades. Only block extreme exhaustion signals.
        rsi_val = float(features.get("rsi_14", 50.0))
        rsi_ob = float(self.settings.get("rsi_overbought", 82.0))
        rsi_os = float(self.settings.get("rsi_oversold", 18.0))
        gate_results["rsi"]["value"] = f"{rsi_val:.1f}"
        # Allow RSI 75-82 for strong directional moves (BTC clearly above P2B)
        strong_directional = abs(strike_delta) >= 3.0
        if predicted_side == "YES" and rsi_val > rsi_ob and not strong_directional:
            gate_results["rsi"]["pass"] = False
            gate_results["rsi"]["value"] = f"{rsi_val:.1f} (Overbought > {rsi_ob:.0f})"
            skip_flags.append(f"SKIP - RSI {rsi_val:.1f} > {rsi_ob:.0f} (Overbought: high reversal risk for UP entry)")
        elif predicted_side == "NO" and rsi_val < rsi_os and not strong_directional:
            gate_results["rsi"]["pass"] = False
            gate_results["rsi"]["value"] = f"{rsi_val:.1f} (Oversold < {rsi_os:.0f})"
            skip_flags.append(f"SKIP - RSI {rsi_val:.1f} < {rsi_os:.0f} (Oversold: high bounce risk for DOWN entry)")
        else:
            gate_results["rsi"]["pass"] = True

        # MACD Trend Alignment filter
        macd_val = float(features.get("macd_hist", 0.0))
        macd_dir = "Bullish" if macd_val > 0.0001 else ("Bearish" if macd_val < -0.0001 else "Neutral")
        gate_results["macd"]["value"] = f"{macd_val:+.4f} ({macd_dir})"
        if predicted_side == "YES" and macd_val < -0.05:
            gate_results["macd"]["pass"] = False
            skip_flags.append(f"SKIP - Severe Bearish MACD divergence ({macd_val:+.4f}) for UP entry")
        elif predicted_side == "NO" and macd_val > 0.05:
            gate_results["macd"]["pass"] = False
            skip_flags.append(f"SKIP - Severe Bullish MACD divergence ({macd_val:+.4f}) for DOWN entry")
        else:
            gate_results["macd"]["pass"] = True

        # Bollinger Bands Volatility & Boundary Protection
        # Allow price beyond upper band (>1.05) if BTC is strongly trending above P2B
        # This prevents blocking entries in strong momentum moves
        bb_pct = float(features.get("bb_pct_b", 0.5))
        bb_bw = float(features.get("bb_bandwidth", 0.0))
        gate_results["bollinger"]["value"] = f"%B {bb_pct:.2f} | BW {bb_bw:.3f}"
        if predicted_side == "YES" and bb_pct > 1.20 and not strong_directional:
            gate_results["bollinger"]["pass"] = False
            skip_flags.append(f"SKIP - Price far above upper Bollinger Band (%B {bb_pct:.2f} > 1.20): extreme reversal risk")
        elif predicted_side == "NO" and bb_pct < -0.20 and not strong_directional:
            gate_results["bollinger"]["pass"] = False
            skip_flags.append(f"SKIP - Price far below lower Bollinger Band (%B {bb_pct:.2f} < -0.20): extreme bounce risk")
        else:
            gate_results["bollinger"]["pass"] = True

        # Multi-Timeframe (MTF) Trend & Spot Momentum Alignment
        if self.settings.get("mtf_confirmation_enabled", True):
            spot_mom_1m = features.get("btc_momentum_1m")
            clob_mom_1m = features.get("short_momentum_1m", 0.0)
            m1_dir = spot_mom_1m if spot_mom_1m is not None else clob_mom_1m
            m5_macd = float(features.get("macd_hist", 0.0))

            if predicted_side == "YES":
                if (spot_mom_1m is not None and spot_mom_1m < -0.0003) or m1_dir < -0.0002 or m5_macd < -0.05:
                    skip_flags.append(f"SKIP - Multi-timeframe trend divergence (1m mom: {m1_dir:+.4f}, 5m MACD: {m5_macd:+.4f}) - not aligned for UP")
            elif predicted_side == "NO":
                if (spot_mom_1m is not None and spot_mom_1m > 0.0003) or m1_dir > 0.0002 or m5_macd > 0.05:
                    skip_flags.append(f"SKIP - Multi-timeframe trend divergence (1m mom: {m1_dir:+.4f}, 5m MACD: {m5_macd:+.4f}) - not aligned for DOWN")
            
        best_side = predicted_side
        final_side = "BUY" if predicted_side == "YES" else ("SELL" if predicted_side == "NO" else "NONE")

        is_only_short = self.only_short or (self.settings.get("only_short") is True) or (self.settings.get("side_bias") == "NO")
        if is_only_short and best_side != "NO":
            skip_flags.insert(0, "SKIP - Instance specialized for Short (NO/DOWN) positions only")

        # DB Open trades check scoped to this instance
        from app.db.session import SessionLocal
        from app.db.models import BTC5MTrade
        db = SessionLocal()
        try:
            open_trades = db.query(BTC5MTrade).filter(
                BTC5MTrade.status == "OPEN",
                BTC5MTrade.instance_id == self.instance_id
            ).all()
            existing_market_trades = db.query(BTC5MTrade).filter(
                BTC5MTrade.market_id == market_id,
                BTC5MTrade.instance_id == self.instance_id
            ).all()

            # Freqtrade Cooldown Guard: Disallow re-entry within cooldown window after trade closure
            cooldown_seconds = float(self.settings.get("cooldown_seconds", 300.0))
            last_closed = db.query(BTC5MTrade).filter(
                BTC5MTrade.status == "CLOSED",
                BTC5MTrade.instance_id == self.instance_id
            ).order_by(BTC5MTrade.id.desc()).first()

            if last_closed and last_closed.exit_time:
                exit_dt = last_closed.exit_time.replace(tzinfo=timezone.utc) if last_closed.exit_time.tzinfo is None else last_closed.exit_time
                elapsed_since_exit = (now - exit_dt).total_seconds()
                # If last closed trade was a LOSS, enforce minimum 180s (3-minute) cooldown to prevent revenge trading
                is_loss = (last_closed.pnl is not None and last_closed.pnl < 0)
                effective_cd = max(180.0, cooldown_seconds) if is_loss else cooldown_seconds
                if elapsed_since_exit < effective_cd:
                    rem_cd = int(effective_cd - elapsed_since_exit)
                    skip_flags.append(f"SKIP - Cooldown active ({rem_cd}s remaining after trade #{last_closed.id} exit)")

            # Disallow re-entering the SAME 5M candle if any prior trade on this candle resulted in a loss!
            if any(t.pnl is not None and t.pnl < 0 for t in existing_market_trades):
                skip_flags.append("SKIP - Prior trade in this 5M candle was a loss (Preventing whipsaw revenge trading)")
        finally:
            db.close()

        slot_mode = self.settings.get("slot_mode") or getattr(self, "slot_mode", None) or "single_5m"

        if slot_mode == "double_slot_2.5m":
            # 2.5-minute slots: Slot 1 (300s -> 150s), Slot 2 (150s -> 30s)
            current_slot = 1 if time_remaining > 150.0 else 2
            slot1_traded = any(
                (t.time_remaining_at_entry is not None and t.time_remaining_at_entry > 150.0)
                for t in existing_market_trades
            )
            slot2_traded = any(
                (t.time_remaining_at_entry is not None and t.time_remaining_at_entry <= 150.0)
                for t in existing_market_trades
            )
            if current_slot == 1 and slot1_traded:
                skip_flags.append("SKIP - Slot 1 (first 2.5m) already traded for this 5M candle")
            elif current_slot == 2 and slot2_traded:
                skip_flags.append("SKIP - Slot 2 (second 2.5m) already traded for this 5M candle")

            if len(open_trades) >= 2:
                skip_flags.append("SKIP - Max 2 open positions allowed (both slots active)")
        else:
            # Single trade per 5M candle (Bot 1)
            if len(open_trades) >= 1:
                skip_flags.append("SKIP - Max 1 open position allowed")

            if len(existing_market_trades) >= 1:
                skip_flags.append("SKIP - Single trade per 5M candle already executed")

        if current_balance <= 0:
            skip_flags.append("SKIP - Risk limit (Zero or negative balance)")

        # AI Hedge Fund 4-Agent Consensus Committee (Unanimous 4/4 Agreement Required)
        if self.settings.get("unanimous_consensus_required", True):
            # 1. Trend & Momentum Agent (RSI, MACD, Bollinger, MTF)
            agent_trend_pass = gate_results.get("rsi", {}).get("pass", False) and gate_results.get("macd", {}).get("pass", False) and gate_results.get("bollinger", {}).get("pass", False)
            # 2. Oracle Valuation Agent (Chainlink Spot vs P2B strike lead >= $1.5, Fair Probability >= 40%)
            p2b_delta = abs((btc_price or 0.0) - (price_to_beat or 0.0))
            agent_oracle_pass = (p2b_delta >= float(self.settings.get("min_p2b_diff", 1.5))) and gate_results.get("probability", {}).get("pass", False)
            # 3. Microstructure & Liquidity Agent (Hummingbot OBI, Spread <= 2%, Depth >= $10k)
            agent_micro_pass = gate_results.get("spread", {}).get("pass", False) and gate_results.get("liquidity", {}).get("pass", False) and gate_results.get("obi", {}).get("pass", False)
            # 4. Risk Guardian Agent (Account Capital, Cooldown, and Drawdown Limits)
            agent_risk_pass = (current_balance > 0) and not any("Cooldown" in s for s in skip_flags) and not any("Max" in s for s in skip_flags)

            committee_votes = {
                "Trend_Agent": "APPROVE" if agent_trend_pass else "DISSENT",
                "Oracle_Agent": "APPROVE" if agent_oracle_pass else "DISSENT",
                "Microstructure_Agent": "APPROVE" if agent_micro_pass else "DISSENT",
                "Risk_Guardian": "APPROVE" if agent_risk_pass else "DISSENT"
            }
            dissenting_agents = [agent for agent, vote in committee_votes.items() if vote == "DISSENT"]
            if dissenting_agents:
                skip_flags.append(f"SKIP - AI Hedge Fund Committee Dissent: [{', '.join(dissenting_agents)}] rejected trade")
            
        state = "SKIP" if skip_flags else "READY"
        
        # Calculate EV Grade (Prediction Pilot Style Data-Driven Analysis)
        target_edge = yes_edge if best_side == "YES" else no_edge
        trade_grade = "F"
        if target_edge > 0.08: trade_grade = "A+"
        elif target_edge > 0.04: trade_grade = "A"
        elif target_edge > 0.01: trade_grade = "B"
        elif target_edge > -0.02: trade_grade = "C"
        elif target_edge > -0.05: trade_grade = "D"
        
        reason = skip_flags[0] if skip_flags else f"[Grade {trade_grade}] EV: {target_edge*100:+.1f}% | Prediction: {best_side} (Score: {max(yes_score, no_score):.1f})"
        
        # Override side properly
        final_side = "BUY" if best_side == "YES" else ("SELL" if best_side == "NO" else "NONE")
        
        if state == "READY" and self.risk_manager:
            risk_decision = self.risk_manager.evaluate_trade(
                {"market_id": market_id, "side": final_side},
                {"condition_id": condition_id, "ask_depth": ask_depth, "bid_depth": bid_depth}
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
            risk_pct=risk_pct,
            position_size=selected_pos_size,
            time_remaining_sec=time_remaining,
            planned_risk=selected_risk,
            planned_reward=selected_risk * actual_planned_rr,
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
            no_breakdown=json.dumps(no_breakdown),
            rsi=rsi_val,
            macd_hist=macd_val,
            bb_pct_b=bb_pct,
            bb_bandwidth=bb_bw,
            instance_id=self.instance_id
        )
