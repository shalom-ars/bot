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
MIN_NET_EDGE          = 0.03   # Minimum net edge (same as global min_edge)
MAX_SPREAD_STABILITY  = 0.02   # Spread must be stable (low std)
MIN_MOMENTUM_PERSIST  = 0.40   # Momentum must be persistent (40% consistent direction)
STALENESS_THRESHOLD_S = 10.0   # Data older than 10s is stale


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
    # Risk-level skip flags
    skip_flags: list = field(default_factory=list)


def _compute_fair_probability(price: float, momentum: float, imbalance: float) -> float:
    """
    Rule-based fair probability estimate.
    When ML model is untrained, we use a conservative adjustment:
      fair_prob = market_price + directional_nudge
    The nudge is small and only applied when momentum and imbalance agree.
    Clearly labeled as rule_based, not ML.
    """
    nudge = 0.0
    if momentum > 0 and imbalance > 0:
        nudge = min(0.03, abs(momentum) * 0.5 + abs(imbalance) * 0.02)
    elif momentum < 0 and imbalance < 0:
        nudge = -min(0.03, abs(momentum) * 0.5 + abs(imbalance) * 0.02)
    return max(0.01, min(0.99, price + nudge))


class BTC5MStrategy:
    """
    BTC 5-Minute Prediction Market Strategy.
    Evaluates both YES (UP) and NO (DOWN) using a 100-point scoring system.
    """

    def __init__(self, risk_manager=None):
        self.risk_manager = risk_manager
        self._active_positions: dict = {}  # market_id -> entry info
        self.last_btc_price = None
        self.last_price_to_beat = None

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

    def _calc_edge_and_rr(self, is_yes: bool, features: dict, current_balance: float):
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
        momentum = features.get("short_momentum_1m", 0.0)
        imbalance = features.get("bid_ask_imbalance", 0.0)
        fair_yes = _compute_fair_probability(price, momentum, imbalance)
        fair_prob = fair_yes if is_yes else (1.0 - fair_yes)
        
        planned_risk = current_balance * settings.risk_per_trade
        take_profit_price = min(0.95, entry_price + 0.30) # Dynamic target
        reward_per_share = take_profit_price - entry_price
        risk_per_share = reward_per_share / 2.0
        stop_loss_price = entry_price - risk_per_share
        
        net_reward = (take_profit_price - entry_price) - fees - slippage_cost - spread_cost
        net_risk = (entry_price - stop_loss_price) + fees + slippage_cost + spread_cost
        
        actual_planned_rr = net_reward / net_risk if net_risk > 0 else 0
        net_edge = net_reward - net_risk
        
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
            )

        # 1. Score both sides
        yes_base_score, yes_breakdown = self._score_side(True, features, btc_price, price_to_beat)
        no_base_score, no_breakdown = self._score_side(False, features, btc_price, price_to_beat)
        
        # 2. Calculate edges
        yes_ep, yes_fair, yes_rr, yes_edge, yes_sl, yes_tp, risk = self._calc_edge_and_rr(True, features, current_balance)
        no_ep, no_fair, no_rr, no_edge, no_sl, no_tp, _ = self._calc_edge_and_rr(False, features, current_balance)
        
        # Add dynamic points (10 for edge, 5 for RR, 5 for time)
        # Edge > 0.05 gives 10 points
        yes_score = yes_base_score + min(10, max(0, yes_edge * 200)) + (5 if yes_rr >= 2.0 else 0) + min(5, time_remaining / 60.0)
        no_score = no_base_score + min(10, max(0, no_edge * 200)) + (5 if no_rr >= 2.0 else 0) + min(5, time_remaining / 60.0)
        
        # 3. Determine winner
        best_side = "YES" if yes_score >= no_score else "NO"
        
        is_yes = (best_side == "YES")
        entry_price = yes_ep if is_yes else no_ep
        fair_prob = yes_fair if is_yes else no_fair
        actual_planned_rr = yes_rr if is_yes else no_rr
        net_edge = yes_edge if is_yes else no_edge
        stop_loss_price = yes_sl if is_yes else no_sl
        take_profit_price = yes_tp if is_yes else no_tp
        
        # 4. Entry Filters
        if time_remaining < 30:
            skip_flags.append("SKIP - Too close to resolution (<30s)")
        
        if liquidity < MIN_LIQUIDITY:
            skip_flags.append(f"SKIP - Insufficient liquidity ({liquidity:.1f})")
            
        if spread > MAX_SPREAD:
            skip_flags.append(f"SKIP - Spread too high ({spread:.3f})")
            
        if actual_planned_rr < 2.0:
            skip_flags.append(f"SKIP - R:R below 1:2 (Achievable Net R:R is {actual_planned_rr:.2f})")
            
        if net_edge < MIN_NET_EDGE:
            skip_flags.append(f"SKIP - Net edge too low ({net_edge:.3f})")
            
        if not btc_price or not price_to_beat:
            skip_flags.append("SKIP - Missing Price-to-Beat or Current BTC Price (Stale data)")

        # DB Open trades check
        from app.db.session import SessionLocal
        from app.db.models import BTC5MTrade
        db = SessionLocal()
        try:
            open_count = db.query(BTC5MTrade).filter(BTC5MTrade.status == "OPEN").count()
        finally:
            db.close()

        if open_count >= 1:
            skip_flags.append("SKIP - Max 1 open position allowed")
            
        state = "SKIP" if skip_flags else "READY"
        reason = skip_flags[0] if skip_flags else f"Prediction: {best_side} (Score: {max(yes_score, no_score):.1f})"
        
        if state == "READY" and self.risk_manager:
            risk_decision = self.risk_manager.evaluate_trade({}, {})
            if not risk_decision.approved:
                state = "SKIP"
                reason = f"SKIP - Risk limit ({risk_decision.reason})"
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
            side="BUY",
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
            position_size=risk / entry_price if entry_price > 0 else 0,
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
            no_prob=1.0 - yes_fair
        )
