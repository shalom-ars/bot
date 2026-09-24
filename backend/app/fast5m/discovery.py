"""
Fast 5M Market Discovery & CLOB Order Book Engine.
Continuously discovers and tracks active 5-minute Up/Down round epochs
for all 7 primary assets: BTC, ETH, SOL, XRP, DOGE, BNB, HYPE.
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import httpx

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API  = "https://clob.polymarket.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


@dataclass
class FastMarketInfo:
    asset: str # BTC, ETH, SOL, XRP, DOGE, BNB, HYPE
    question: str
    condition_id: str
    up_token_id: str # Outcome 0 ("Up" / YES)
    down_token_id: str # Outcome 1 ("Down" / NO)
    epoch_bucket: int # Unix timestamp of epoch start
    start_time: datetime
    end_time: datetime
    time_remaining_sec: float = 0.0
    # Live Polymarket CLOB book stats
    up_bid: float = 0.50
    up_ask: float = 0.51
    up_mid: float = 0.505
    down_bid: float = 0.49
    down_ask: float = 0.50
    down_mid: float = 0.495
    spread: float = 0.01
    up_bid_depth: float = 0.0
    up_ask_depth: float = 0.0
    down_bid_depth: float = 0.0
    down_ask_depth: float = 0.0
    total_liquidity: float = 0.0
    orderbook_imbalance: float = 0.0 # -1.0 to 1.0 (positive = buying pressure for UP)
    is_active: bool = True
    last_refresh_ts: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "question": self.question,
            "condition_id": self.condition_id,
            "up_token_id": self.up_token_id,
            "down_token_id": self.down_token_id,
            "epoch_bucket": self.epoch_bucket,
            "start_time_iso": self.start_time.isoformat(),
            "end_time_iso": self.end_time.isoformat(),
            "time_remaining_sec": round(self.time_remaining_sec, 1),
            "up_bid": self.up_bid,
            "up_ask": self.up_ask,
            "up_mid": round(self.up_mid, 3),
            "down_bid": self.down_bid,
            "down_ask": self.down_ask,
            "down_mid": round(self.down_mid, 3),
            "spread": round(self.spread, 4),
            "up_bid_depth": round(self.up_bid_depth, 2),
            "up_ask_depth": round(self.up_ask_depth, 2),
            "total_liquidity": round(self.total_liquidity, 2),
            "orderbook_imbalance": round(self.orderbook_imbalance, 3),
            "is_active": self.is_active,
        }


class FastMarketTracker:
    """
    Manages active 5-minute Polymarket round discoveries and order book streams for 7 assets.
    """
    def __init__(self):
        self.markets: Dict[str, FastMarketInfo] = {} # asset -> FastMarketInfo
        self.running: bool = False
        self._poll_task: Optional[asyncio.Task] = None
        self._book_task: Optional[asyncio.Task] = None

    async def start(self):
        if self.running:
            return
        self.running = True
        logger.info("[Fast5M Discovery] Starting market tracking for all 7 assets...")
        # Initial discovery
        await self.refresh_all_markets()
        self._poll_task = asyncio.create_task(self._discovery_loop())
        self._book_task = asyncio.create_task(self._orderbook_loop())

    async def stop(self):
        self.running = False
        for t in [self._poll_task, self._book_task]:
            if t and not t.done():
                t.cancel()
        logger.info("[Fast5M Discovery] Stopped.")

    async def _discovery_loop(self):
        """Discovers the active and next 5m epoch market metadata every 8 seconds."""
        while self.running:
            try:
                await self.refresh_all_markets()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[Fast5M Discovery] Loop error: {e}")
            await asyncio.sleep(8.0)

    async def _orderbook_loop(self):
        """Fetches CLOB orderbook for all active markets every 1.5 seconds."""
        while self.running:
            try:
                if self.markets:
                    await self._refresh_orderbooks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[Fast5M Discovery] Orderbook loop error: {e}")
            await asyncio.sleep(1.5)

    async def refresh_all_markets(self):
        """Discover active 5m markets for all 7 assets."""
        from app.fast5m.oracle import SUPPORTED_ASSETS
        now_ts = int(time.time())
        current_bucket = now_ts - (now_ts % 300)
        
        async with httpx.AsyncClient(timeout=4.0, headers={"User-Agent": USER_AGENT}) as client:
            tasks = [
                self._discover_asset_market(client, asset.lower(), current_bucket)
                for asset in SUPPORTED_ASSETS
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, FastMarketInfo):
                    self.markets[res.asset] = res

    async def _discover_asset_market(self, client: httpx.AsyncClient, asset_lower: str, bucket: int) -> Optional[FastMarketInfo]:
        """Fetch market for a specific asset and 5m bucket."""
        asset_upper = asset_lower.upper()
        # Check current bucket, fallback to next bucket if current is within last 10s
        buckets = [bucket, bucket + 300]
        now = datetime.now(timezone.utc)
        
        for b in buckets:
            slug = f"{asset_lower}-updown-5m-{b}"
            url = f"{GAMMA_API}/events?slug={slug}"
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        event = data[0]
                        markets = event.get("markets", [])
                        if markets:
                            m = markets[0]
                            clob_token_ids = m.get("clobTokenIds") or []
                            if isinstance(clob_token_ids, str):
                                clob_token_ids = json.loads(clob_token_ids)
                            
                            if len(clob_token_ids) >= 2:
                                up_token = clob_token_ids[0]
                                down_token = clob_token_ids[1]
                                condition_id = m.get("conditionId", "")
                                question = m.get("question", "") or event.get("title", "")
                                
                                start_dt = datetime.fromtimestamp(b, tz=timezone.utc)
                                end_dt = datetime.fromtimestamp(b + 300, tz=timezone.utc)
                                remaining = max(0.0, (end_dt - now).total_seconds())

                                existing = self.markets.get(asset_upper)
                                if existing and existing.epoch_bucket == b:
                                    existing.time_remaining_sec = remaining
                                    return existing

                                info = FastMarketInfo(
                                    asset=asset_upper,
                                    question=question,
                                    condition_id=condition_id,
                                    up_token_id=up_token,
                                    down_token_id=down_token,
                                    epoch_bucket=b,
                                    start_time=start_dt,
                                    end_time=end_dt,
                                    time_remaining_sec=remaining,
                                    is_active=True,
                                    last_refresh_ts=time.time()
                                )
                                return info
            except Exception as e:
                logger.debug(f"[Fast5M Discovery] Error fetching {slug}: {e}")
        return None

    async def _refresh_orderbooks(self):
        """Concurrently fetch live CLOB depth for all tracked asset markets."""
        now = datetime.now(timezone.utc)
        async with httpx.AsyncClient(timeout=2.5, headers={"User-Agent": USER_AGENT}) as client:
            tasks = []
            for asset, m in list(self.markets.items()):
                m.time_remaining_sec = max(0.0, (m.end_time - now).total_seconds())
                tasks.append(self._fetch_single_orderbook(client, m))
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_single_orderbook(self, client: httpx.AsyncClient, market: FastMarketInfo):
        """Fetch CLOB depth for UP token and compute live mid, spread, depth, and imbalance."""
        try:
            url = f"{CLOB_API}/book?token_id={market.up_token_id}"
            resp = await client.get(url)
            if resp.status_code == 200:
                book = resp.json()
                bids = book.get("bids", [])
                asks = book.get("asks", [])
                
                up_bid = float(bids[0]["price"]) if bids else 0.49
                up_ask = float(asks[0]["price"]) if asks else 0.51
                up_mid = (up_bid + up_ask) / 2.0
                
                bid_depth = sum(float(b.get("size", 0)) * float(b.get("price", 0)) for b in bids[:5])
                ask_depth = sum(float(a.get("size", 0)) * float(a.get("price", 0)) for a in asks[:5])
                
                market.up_bid = up_bid
                market.up_ask = up_ask
                market.up_mid = up_mid
                market.down_bid = round(max(0.01, 1.0 - up_ask), 4)
                market.down_ask = round(min(0.99, 1.0 - up_bid), 4)
                market.down_mid = (market.down_bid + market.down_ask) / 2.0
                market.spread = max(0.001, up_ask - up_bid)
                market.up_bid_depth = bid_depth
                market.up_ask_depth = ask_depth
                market.total_liquidity = bid_depth + ask_depth
                
                # Orderbook Imbalance: (bid_depth - ask_depth) / (bid_depth + ask_depth)
                if (bid_depth + ask_depth) > 0:
                    market.orderbook_imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)
                else:
                    market.orderbook_imbalance = 0.0
                
                market.last_refresh_ts = time.time()
        except Exception:
            pass

    def get_market(self, asset: str) -> Optional[FastMarketInfo]:
        return self.markets.get(asset.upper())

    def get_all_markets(self) -> Dict[str, Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        result = {}
        for asset, m in self.markets.items():
            m.time_remaining_sec = max(0.0, (m.end_time - now).total_seconds())
            result[asset] = m.to_dict()
        return result


# Global singleton instance
fast_markets = FastMarketTracker()
