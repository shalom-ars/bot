"""
BTC 5M Feature Engine.

Computes short-horizon features specifically designed for
5-minute Polymarket prediction market trading.

Features are derived ONLY from:
- Live CLOB orderbook data (bid, ask, depth, imbalance)
- Price history in the in-memory ring buffer
- Time-to-resolution

No external price feeds. Polymarket-only.
"""
import math
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Deque

logger = logging.getLogger(__name__)

# Ring buffer size for price/imbalance history
HISTORY_SIZE = 60   # 60 ticks per market max


@dataclass
class PricePoint:
    timestamp: datetime
    price: float
    bid: float
    ask: float
    spread: float
    bid_depth: float
    ask_depth: float
    imbalance: float


class BTC5MFeatureBuffer:
    """Per-market rolling history buffer."""
    def __init__(self):
        self.history: Deque[PricePoint] = deque(maxlen=HISTORY_SIZE)

    def push(self, point: PricePoint):
        self.history.append(point)

    def prices(self):
        return [p.price for p in self.history]

    def imbalances(self):
        return [p.imbalance for p in self.history]

    def spreads(self):
        return [p.spread for p in self.history]


class BTC5MFeatureEngine:
    """
    Computes features for BTC 5M markets.
    Each market has its own buffer keyed by market_id.
    """
    def __init__(self):
        self._buffers: dict[str, BTC5MFeatureBuffer] = {}

    def _get_buffer(self, market_id: str) -> BTC5MFeatureBuffer:
        if market_id not in self._buffers:
            self._buffers[market_id] = BTC5MFeatureBuffer()
        return self._buffers[market_id]

    def update_and_compute(
        self,
        market_id: str,
        price: float,
        bid: float,
        ask: float,
        spread: float,
        bid_depth: float,
        ask_depth: float,
        imbalance: float,
        time_remaining_sec: float,
    ) -> dict:
        """
        Push new tick data and return computed features dict.
        """
        buf = self._get_buffer(market_id)
        now = datetime.now(timezone.utc)
        buf.push(PricePoint(
            timestamp=now,
            price=price,
            bid=bid,
            ask=ask,
            spread=spread,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            imbalance=imbalance,
        ))

        prices = buf.prices()
        imbalances = buf.imbalances()
        spreads_hist = buf.spreads()

        n = len(prices)
        features = {}

        # ── MOMENTUM & RETURNS ──────────────────────────────
        # 1-tick return (most recent)
        features["return_1"] = (prices[-1] - prices[-2]) / (prices[-2] + 1e-9) if n >= 2 else 0.0
        # 3-tick return
        features["return_3"] = (prices[-1] - prices[-4]) / (prices[-4] + 1e-9) if n >= 4 else 0.0
        # 5-tick return
        features["return_5"] = (prices[-1] - prices[-6]) / (prices[-6] + 1e-9) if n >= 6 else 0.0
        # 10-tick return
        features["return_10"] = (prices[-1] - prices[-11]) / (prices[-11] + 1e-9) if n >= 11 else 0.0

        # Short momentum: EWM-style on last 5 returns
        if n >= 3:
            recent = [prices[i] - prices[i-1] for i in range(max(1, n-5), n)]
            features["short_momentum_1m"] = sum(recent) / (len(recent) + 1e-9)
        else:
            features["short_momentum_1m"] = 0.0

        # Momentum acceleration (change in momentum)
        if n >= 5:
            mom_prev = sum(prices[i] - prices[i-1] for i in range(n-4, n-2)) / 2.0
            mom_curr = sum(prices[i] - prices[i-1] for i in range(n-2, n)) / 2.0
            features["momentum_acceleration"] = mom_curr - mom_prev
        else:
            features["momentum_acceleration"] = 0.0

        # Price direction (sign of last 3 moves)
        if n >= 4:
            moves = [prices[i] - prices[i-1] for i in range(n-3, n)]
            features["price_direction"] = sum(1 if m > 0 else -1 if m < 0 else 0 for m in moves) / 3.0
        else:
            features["price_direction"] = 0.0

        # Momentum persistence (sign consistency)
        if n >= 6:
            last_moves = [prices[i] - prices[i-1] for i in range(n-5, n)]
            signs = [1 if m > 0 else -1 if m < 0 else 0 for m in last_moves]
            features["momentum_persistence"] = abs(sum(signs)) / (len(signs) + 1e-9)
        else:
            features["momentum_persistence"] = 0.0

        # ── RELATIVE STRENGTH INDEX (RSI-14) ─────────────
        # 14-period RSI with overbought @ 70 and oversold @ 30
        if n >= 15:
            period = 14
            changes = [prices[i] - prices[i-1] for i in range(n - period, n)]
            gains = [c for c in changes if c > 0]
            losses = [-c for c in changes if c < 0]
            avg_gain = sum(gains) / float(period)
            avg_loss = sum(losses) / float(period)
            if avg_loss == 0:
                features["rsi_14"] = 100.0 if avg_gain > 0 else 50.0
            else:
                rs = avg_gain / avg_loss
                features["rsi_14"] = round(100.0 - (100.0 / (1.0 + rs)), 2)
        elif n >= 5:
            # Approximate RSI for earlier ticks until 14 periods accumulate
            p_sub = n - 1
            changes = [prices[i] - prices[i-1] for i in range(1, n)]
            gains = [c for c in changes if c > 0]
            losses = [-c for c in changes if c < 0]
            avg_gain = sum(gains) / float(p_sub)
            avg_loss = sum(losses) / float(p_sub)
            if avg_loss == 0:
                features["rsi_14"] = 100.0 if avg_gain > 0 else 50.0
            else:
                rs = avg_gain / avg_loss
                features["rsi_14"] = round(100.0 - (100.0 / (1.0 + rs)), 2)
        else:
            features["rsi_14"] = 50.0  # Neutral midpoint

        # ── ORDERBOOK ───────────────────────────────────────
        features["bid_ask_imbalance"] = imbalance
        features["depth_imbalance"] = (bid_depth - ask_depth) / (bid_depth + ask_depth + 1e-9)
        features["executable_liquidity"] = min(bid_depth, ask_depth)
        features["spread"] = spread
        features["spread_pct"] = spread / (ask + 1e-9) if ask > 0 else 1.0

        # Spread stability (std of recent spreads)
        if len(spreads_hist) >= 3:
            mean_s = sum(spreads_hist[-5:]) / len(spreads_hist[-5:])
            var_s = sum((x - mean_s)**2 for x in spreads_hist[-5:]) / len(spreads_hist[-5:])
            features["spread_stability"] = math.sqrt(var_s)
        else:
            features["spread_stability"] = spread

        # Orderbook pressure (imbalance trend)
        if len(imbalances) >= 3:
            features["ob_pressure"] = imbalances[-1] - imbalances[-3]
        else:
            features["ob_pressure"] = 0.0

        # ── VOLATILITY ──────────────────────────────────────
        if n >= 5:
            rets = [prices[i] - prices[i-1] for i in range(1, n)]
            recent_rets = rets[-10:]
            mean_r = sum(recent_rets) / len(recent_rets)
            var_r = sum((r - mean_r)**2 for r in recent_rets) / (len(recent_rets) + 1e-9)
            features["rolling_volatility"] = math.sqrt(var_r)
        else:
            features["rolling_volatility"] = 0.0

        # Volatility expansion: current vol vs baseline
        if n >= 15:
            rets_all = [prices[i] - prices[i-1] for i in range(1, n)]
            mean_all = sum(rets_all) / len(rets_all)
            var_all = sum((r - mean_all)**2 for r in rets_all) / len(rets_all)
            baseline_vol = math.sqrt(var_all)
            curr_vol = features["rolling_volatility"]
            features["volatility_expansion"] = curr_vol / (baseline_vol + 1e-9) - 1.0
        else:
            features["volatility_expansion"] = 0.0

        # Abnormal movement: price move vs rolling vol
        if features["rolling_volatility"] > 0 and n >= 2:
            features["abnormal_move"] = abs(prices[-1] - prices[-2]) / (features["rolling_volatility"] + 1e-9)
        else:
            features["abnormal_move"] = 0.0

        # ── MICROSTRUCTURE ───────────────────────────────────
        features["mid_price"] = (bid + ask) / 2 if bid > 0 and ask > 0 else price

        # Price acceleration (second derivative)
        if n >= 4:
            d2 = (prices[-1] - 2*prices[-2] + prices[-3]) if n >= 3 else 0.0
            features["price_acceleration"] = d2
        else:
            features["price_acceleration"] = 0.0

        # Distance from 50% (centre)
        features["distance_from_50"] = price - 0.5

        # ── TIME ─────────────────────────────────────────────
        features["time_remaining_sec"] = max(0, time_remaining_sec)
        # Fraction of time remaining (relative to 300s = 5min)
        features["time_remaining_fraction"] = min(1.0, time_remaining_sec / 300.0)
        # Urgency: 1.0 = much time left, 0.0 = no time
        features["urgency"] = 1.0 - features["time_remaining_fraction"]

        return features
