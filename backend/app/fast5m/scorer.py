"""
Fast 5M Real-Time Directional Scorer & Asset Ranker.
Evaluates all 7 fast 5-minute assets (BTC, ETH, SOL, XRP, DOGE, BNB, HYPE)
based on:
1. Oracle Price Delta & Expiration Velocity (40 pts)
2. Polymarket Order Book Imbalances & Liquidity (30 pts)
3. Micro-Momentum & Multi-Timeframe Velocity Confluence (30 pts)

Outputs:
- Direction ("UP", "DOWN", "NEUTRAL")
- Directional Score (0 - 100)
- Composite Confidence (0 - 100%)
- Live 1 - 7 Cross-Asset Ranking
- Top-Ranked #1 Opportunity
"""
import logging
import math
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from app.fast5m.oracle import fast_oracle, SUPPORTED_ASSETS
from app.fast5m.discovery import fast_markets, FastMarketInfo

logger = logging.getLogger(__name__)


@dataclass
class ScoredAsset:
    asset: str
    direction: str # "UP", "DOWN", "NEUTRAL"
    composite_score: float # 0 - 100
    confidence: float # 0 - 100%
    delta_score: float = 0.0 # 0 - 40
    obi_score: float = 0.0 # 0 - 30
    momentum_score: float = 0.0 # 0 - 30
    rank: int = 1 # 1 to 7
    delta: float = 0.0
    delta_pct: float = 0.0
    live_price: float = 0.0
    strike_price: float = 0.0
    latency_ms: float = 0.0
    time_remaining_sec: float = 0.0
    up_share_price: float = 0.50
    down_share_price: float = 0.50
    spread: float = 0.01
    liquidity: float = 0.0
    orderbook_imbalance: float = 0.0
    velocity_10s: float = 0.0
    velocity_30s: float = 0.0
    reason: str = ""
    target_token_id: str = ""
    is_tradable: bool = True
    rejection_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "direction": self.direction,
            "composite_score": round(self.composite_score, 1),
            "confidence": round(self.confidence, 1),
            "delta_score": round(self.delta_score, 1),
            "obi_score": round(self.obi_score, 1),
            "momentum_score": round(self.momentum_score, 1),
            "rank": self.rank,
            "delta": round(self.delta, 4) if abs(self.delta) < 1 else round(self.delta, 2),
            "delta_pct": round(self.delta_pct, 4),
            "live_price": round(self.live_price, 4) if self.live_price < 10 else round(self.live_price, 2),
            "strike_price": round(self.strike_price, 4) if self.strike_price < 10 else round(self.strike_price, 2),
            "latency_ms": self.latency_ms,
            "time_remaining_sec": round(self.time_remaining_sec, 1),
            "up_share_price": self.up_share_price,
            "down_share_price": self.down_share_price,
            "spread": round(self.spread, 4),
            "liquidity": round(self.liquidity, 2),
            "orderbook_imbalance": round(self.orderbook_imbalance, 3),
            "velocity_10s": round(self.velocity_10s, 4),
            "velocity_30s": round(self.velocity_30s, 4),
            "reason": self.reason,
            "target_token_id": self.target_token_id,
            "is_tradable": self.is_tradable,
            "rejection_reason": self.rejection_reason,
        }


class FastScorer:
    """
    Computes real-time directional confluence scores and ranks all 7 fast markets.
    """
    def score_all_assets(self, confidence_threshold: float = 70.0) -> List[ScoredAsset]:
        scored_list: List[ScoredAsset] = []

        for asset in SUPPORTED_ASSETS:
            oracle_state = fast_oracle.get_asset_state(asset)
            market_info = fast_markets.get_market(asset)
            
            if not oracle_state or oracle_state.live_price <= 0:
                continue

            scored = self._score_single_asset(asset, oracle_state, market_info, confidence_threshold)
            scored_list.append(scored)

        # Sort by composite confidence descending
        scored_list.sort(key=lambda x: (x.is_tradable, x.confidence), reverse=True)

        # Assign ranks 1 to 7
        for idx, item in enumerate(scored_list, start=1):
            item.rank = idx

        return scored_list

    def _score_single_asset(
        self,
        asset: str,
        oracle: Any,
        market: Optional[FastMarketInfo],
        threshold: float
    ) -> ScoredAsset:
        delta = oracle.delta
        delta_pct = oracle.delta_pct
        live_price = oracle.live_price
        strike_price = oracle.strike_price
        latency_ms = oracle.latency_ms
        v10 = oracle.velocity_10s
        v30 = oracle.velocity_30s
        v60 = oracle.velocity_60s
        
        time_rem = market.time_remaining_sec if market else 180.0
        up_price = market.up_ask if market else 0.50
        down_price = market.down_ask if market else 0.50
        spread = market.spread if market else 0.02
        liquidity = market.total_liquidity if market else 500.0
        imbalance = market.orderbook_imbalance if market else 0.0

        # Sub-Score 1: Oracle Delta & Expiration Velocity (0 - 40 pts)
        # Closer to expiration with established delta yields highest confidence
        time_factor = max(0.5, min(1.5, 300.0 / (time_rem + 60.0)))
        
        # Normalize delta_pct based on typical 5m volatility (0.15% is significant for 5m)
        vol_scale = 0.12 if asset in ("BTC", "ETH", "BNB") else 0.25 # higher beta for SOL, XRP, DOGE, HYPE
        normalized_delta = (delta_pct / vol_scale) * time_factor
        
        up_delta_score = 20.0 + min(20.0, max(-20.0, normalized_delta * 12.0))
        down_delta_score = 20.0 + min(20.0, max(-20.0, -normalized_delta * 12.0))

        # Add velocity continuation bonus
        if v10 > 0.02 and v30 > 0.01:
            up_delta_score = min(40.0, up_delta_score + 5.0)
            down_delta_score = max(0.0, down_delta_score - 5.0)
        elif v10 < -0.02 and v30 < -0.01:
            down_delta_score = min(40.0, down_delta_score + 5.0)
            up_delta_score = max(0.0, up_delta_score - 5.0)

        # Sub-Score 2: Order Book Imbalance & Depth (0 - 30 pts)
        # Imbalance is in range [-1.0, 1.0]
        up_ob_score = 15.0 + (imbalance * 12.0)
        down_ob_score = 15.0 - (imbalance * 12.0)
        
        # Spread penalty
        spread_penalty = max(0.0, (spread - 0.02) * 100.0)
        up_ob_score = max(0.0, min(30.0, up_ob_score - spread_penalty))
        down_ob_score = max(0.0, min(30.0, down_ob_score - spread_penalty))

        # Sub-Score 3: Technical Indicators & Momentum Confluence (0 - 30 pts)
        # Evaluates RSI (14), Bollinger Bands (%B), EMA Trend (9/21), MACD, and micro-velocities
        rsi = getattr(oracle, 'rsi_14', 50.0)
        bb_b = getattr(oracle, 'bb_pct_b', 0.5)
        ema_tr = getattr(oracle, 'ema_trend', 0.0)
        macd = getattr(oracle, 'macd_hist', 0.0)

        up_tech_pts = 15.0
        down_tech_pts = 15.0

        # RSI factor
        if rsi > 55.0:
            up_tech_pts += min(5.0, (rsi - 50.0) * 0.25)
            down_tech_pts -= min(4.0, (rsi - 50.0) * 0.2)
        elif rsi < 45.0:
            down_tech_pts += min(5.0, (50.0 - rsi) * 0.25)
            up_tech_pts -= min(4.0, (50.0 - rsi) * 0.2)

        # EMA Trend & MACD factor
        if ema_tr > 0.05 and macd > 0:
            up_tech_pts += 5.0
            down_tech_pts -= 4.0
        elif ema_tr < -0.05 and macd < 0:
            down_tech_pts += 5.0
            up_tech_pts -= 4.0

        # Bollinger Bands %B factor
        if bb_b > 0.6:
            up_tech_pts += 3.0
        elif bb_b < 0.4:
            down_tech_pts += 3.0

        # Multi-timeframe velocity agreement (10s, 30s, 60s)
        if v10 > 0 and v30 > 0 and v60 > 0:
            up_tech_pts += 7.0
            down_tech_pts -= 6.0
        elif v10 < 0 and v30 < 0 and v60 < 0:
            down_tech_pts += 7.0
            up_tech_pts -= 6.0
        elif v10 > 0 and v30 > 0:
            up_tech_pts += 4.0
            down_tech_pts -= 3.0
        elif v10 < 0 and v30 < 0:
            down_tech_pts += 4.0
            up_tech_pts -= 3.0

        up_mom_score = max(0.0, min(30.0, up_tech_pts))
        down_mom_score = max(0.0, min(30.0, down_tech_pts))

        # Total Scores (0 - 100)
        total_up = round(min(100.0, max(0.0, up_delta_score + up_ob_score + up_mom_score)), 1)
        total_down = round(min(100.0, max(0.0, down_delta_score + down_ob_score + down_mom_score)), 1)

        # Direction and Composite Confidence
        if total_up > total_down and total_up >= 50.0:
            direction = "UP"
            confidence = total_up
            chosen_delta_score = up_delta_score
            chosen_obi_score = up_ob_score
            chosen_mom_score = up_mom_score
            target_token = market.up_token_id if market else ""
            reason = f"Delta +{delta_pct:.3f}% (Sc:{up_delta_score:.1f}/40) | OBI:{imbalance:+.2f} (Sc:{up_ob_score:.1f}/30) | Mom (Sc:{up_mom_score:.1f}/30)"
        elif total_down > total_up and total_down >= 50.0:
            direction = "DOWN"
            confidence = total_down
            chosen_delta_score = down_delta_score
            chosen_obi_score = down_ob_score
            chosen_mom_score = down_mom_score
            target_token = market.down_token_id if market else ""
            reason = f"Delta {delta_pct:.3f}% (Sc:{down_delta_score:.1f}/40) | OBI:{imbalance:+.2f} (Sc:{down_ob_score:.1f}/30) | Mom (Sc:{down_mom_score:.1f}/30)"
        else:
            direction = "NEUTRAL"
            confidence = max(total_up, total_down)
            chosen_delta_score = up_delta_score if total_up >= total_down else down_delta_score
            chosen_obi_score = up_ob_score if total_up >= total_down else down_ob_score
            chosen_mom_score = up_mom_score if total_up >= total_down else down_mom_score
            target_token = ""
            reason = "Chop / Insufficient directional edge"

        # Tradability checks
        is_tradable = True
        rejection_reason = ""

        if not market:
            is_tradable = False
            rejection_reason = "No active Polymarket 5m epoch"
        elif time_rem < 20.0:
            is_tradable = False
            rejection_reason = f"Too close to round resolution ({time_rem:.0f}s)"
        elif time_rem > 280.0:
            is_tradable = False
            rejection_reason = f"Waiting for round to mature ({time_rem:.0f}s)"
        elif spread > 0.20:
            is_tradable = False
            rejection_reason = f"Spread too wide ({spread*100:.1f}%)"
        elif confidence < threshold:
            is_tradable = False
            rejection_reason = f"Confidence {confidence:.1f} < threshold {threshold:.1f}"

        return ScoredAsset(
            asset=asset,
            direction=direction,
            composite_score=confidence,
            confidence=confidence,
            delta_score=chosen_delta_score,
            obi_score=chosen_obi_score,
            momentum_score=chosen_mom_score,
            rank=99,
            delta=delta,
            delta_pct=delta_pct,
            live_price=live_price,
            strike_price=strike_price,
            latency_ms=latency_ms,
            time_remaining_sec=time_rem,
            up_share_price=up_price,
            down_share_price=down_price,
            spread=spread,
            liquidity=liquidity,
            orderbook_imbalance=imbalance,
            velocity_10s=v10,
            velocity_30s=v30,
            reason=reason,
            target_token_id=target_token,
            is_tradable=is_tradable,
            rejection_reason=rejection_reason,
        )


# Global singleton instance
fast_scorer = FastScorer()
