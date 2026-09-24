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
    rank: int # 1 to 7
    delta: float
    delta_pct: float
    live_price: float
    strike_price: float
    latency_ms: float
    time_remaining_sec: float
    up_share_price: float
    down_share_price: float
    spread: float
    liquidity: float
    orderbook_imbalance: float
    velocity_10s: float
    velocity_30s: float
    reason: str
    target_token_id: str
    is_tradable: bool
    rejection_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "direction": self.direction,
            "composite_score": round(self.composite_score, 1),
            "confidence": round(self.confidence, 1),
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

        # Sub-Score 3: Micro-Momentum Confluence (0 - 30 pts)
        # 10s, 30s, 60s velocity agreement
        up_mom_score = 15.0
        down_mom_score = 15.0

        if v10 > 0 and v30 > 0 and v60 > 0:
            up_mom_score += 12.0
            down_mom_score -= 10.0
        elif v10 < 0 and v30 < 0 and v60 < 0:
            down_mom_score += 12.0
            up_mom_score -= 10.0
        elif v10 > 0 and v30 > 0:
            up_mom_score += 7.0
            down_mom_score -= 6.0
        elif v10 < 0 and v30 < 0:
            down_mom_score += 7.0
            up_mom_score -= 6.0

        up_mom_score = max(0.0, min(30.0, up_mom_score))
        down_mom_score = max(0.0, min(30.0, down_mom_score))

        # Total Scores (0 - 100)
        total_up = round(min(100.0, max(0.0, up_delta_score + up_ob_score + up_mom_score)), 1)
        total_down = round(min(100.0, max(0.0, down_delta_score + down_ob_score + down_mom_score)), 1)

        # Direction and Composite Confidence
        if total_up > total_down and total_up >= 50.0:
            direction = "UP"
            confidence = total_up
            target_token = market.up_token_id if market else ""
            reason = f"Delta +{delta_pct:.3f}% | v10: +{v10:.3f}% | OBI: {imbalance:+.2f}"
        elif total_down > total_up and total_down >= 50.0:
            direction = "DOWN"
            confidence = total_down
            target_token = market.down_token_id if market else ""
            reason = f"Delta {delta_pct:.3f}% | v10: {v10:.3f}% | OBI: {imbalance:+.2f}"
        else:
            direction = "NEUTRAL"
            confidence = max(total_up, total_down)
            target_token = ""
            reason = "Chop / Insufficient directional edge"

        # Tradability checks
        is_tradable = True
        rejection_reason = ""

        if not market:
            is_tradable = False
            rejection_reason = "No active Polymarket 5m epoch"
        elif time_rem < 25.0:
            is_tradable = False
            rejection_reason = f"Too close to round resolution ({time_rem:.0f}s)"
        elif time_rem > 275.0:
            is_tradable = False
            rejection_reason = f"Waiting for round to mature ({time_rem:.0f}s)"
        elif spread > 0.06:
            is_tradable = False
            rejection_reason = f"Spread too wide ({spread*100:.1f}%)"
        elif liquidity < 50.0:
            is_tradable = False
            rejection_reason = f"Low book depth (${liquidity:.0f})"
        elif confidence < threshold:
            is_tradable = False
            rejection_reason = f"Confidence {confidence:.1f} < threshold {threshold:.1f}"

        return ScoredAsset(
            asset=asset,
            direction=direction,
            composite_score=confidence,
            confidence=confidence,
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
