import aiohttp
import asyncio
import logging
from datetime import datetime
from app.config import settings
from app.db.schemas import MarketTick

logger = logging.getLogger(__name__)

class PolymarketConnector:
    def __init__(self):
        self.gamma_api_url = "https://gamma-api.polymarket.com"
        self.clob_api_url = "https://clob.polymarket.com"
        self.session = None
        self.is_stale = True
        self.last_update = None
        self.callbacks = []

    def register_callback(self, callback):
        self.callbacks.append(callback)

    async def connect(self):
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=10)
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def disconnect(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def _request_with_retry(self, url, max_retries=3):
        delay = settings.reconnect_delay_seconds
        for attempt in range(max_retries):
            try:
                if not self.session:
                    await self.connect()
                
                async with self.session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        logger.warning(f"Polymarket Rate Limit: {resp.status}. Retrying in {delay}s...")
                    else:
                        logger.error(f"Polymarket HTTP {resp.status} on {url}")
            except Exception as e:
                logger.error(f"Polymarket Network Error: {e}. Retrying in {delay}s...")
            
            self.is_stale = True
            await asyncio.sleep(delay)
            delay = min(delay * 2, settings.max_reconnect_delay_seconds)
        
        return None

    async def get_active_markets(self, limit=50):
        if not settings.polymarket_enabled:
            return []
        
        url = f"{self.gamma_api_url}/events?limit={limit}&active=true&closed=false"
        data = await self._request_with_retry(url)
        markets = []
        if data:
            for event in data:
                for market in event.get('markets', []):
                    markets.append(market)
        return markets

    async def fetch_market_data(self, token_id):
        if not settings.polymarket_enabled:
            return None
            
        url = f"{self.clob_api_url}/book?token_id={token_id}"
        req_start = datetime.utcnow()
        data = await self._request_with_retry(url, max_retries=1)
        req_end = datetime.utcnow()
        
        if data and isinstance(data, dict):
            bids = data.get('bids', [])
            asks = data.get('asks', [])
            
            best_bid = float(bids[0].get('price', 0)) if bids else 0.0
            best_ask = float(asks[0].get('price', 0)) if asks else 0.0
            
            if best_bid > 0 and best_ask > 0:
                price = (best_bid + best_ask) / 2
                spread = best_ask - best_bid
            else:
                price = 0.0
                spread = 1.0  # Extremely wide spread to fail all quality checks
                
            bid_depth = sum(float(b.get('size', 0)) for b in bids)
            ask_depth = sum(float(a.get('size', 0)) for a in asks)
            imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth + 1e-9)

            tick = MarketTick(
                source="POLYMARKET",
                symbol=token_id,
                market_id=token_id,
                event_timestamp=req_start,
                received_timestamp=req_end,
                price=price,
                bid=best_bid,
                ask=best_ask,
                spread=spread,
                volume=0.0, # We'd need a separate trades endpoint for accurate volume
                liquidity=bid_depth + ask_depth,
                imbalance=imbalance,
                bid_depth=bid_depth,
                ask_depth=ask_depth
            )
            
            self.is_stale = False
            self.last_update = req_end
            
            for cb in self.callbacks:
                await cb(tick)
                
            return price
            
        self.is_stale = True
        return None

    async def fetch_markets_books(self, token_ids):
        if not settings.polymarket_enabled or not token_ids:
            return []
            
        url = f"{self.clob_api_url}/books"
        req_start = datetime.utcnow()
        payload = [{"token_id": t} for t in token_ids]
        
        delay = settings.reconnect_delay_seconds
        data = None
        for attempt in range(3):
            try:
                if not self.session: await self.connect()
                async with self.session.post(url, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        break
                    elif resp.status == 429:
                        logger.warning(f"Rate Limit: {resp.status}")
                    else:
                        logger.error(f"HTTP {resp.status} on {url}")
            except Exception as e:
                pass
            await asyncio.sleep(delay)
            delay = min(delay * 2, settings.max_reconnect_delay_seconds)
            
        req_end = datetime.utcnow()
        results = []
        if data and isinstance(data, list):
            self.is_stale = False
            self.last_update = req_end
            
            for book in data:
                asset_id = book.get('asset_id')
                if not asset_id: continue
                
                bids = book.get('bids', [])
                asks = book.get('asks', [])
                
                best_bid = float(bids[0].get('price', 0)) if bids else 0.0
                best_ask = float(asks[0].get('price', 1.0)) if asks else 1.0
                
                if best_bid > 0 and best_ask > 0 and best_ask < 1.0:
                    price = (best_bid + best_ask) / 2
                    spread = best_ask - best_bid
                else:
                    price = 0.0
                    spread = 1.0  # Extremely wide spread to fail all quality checks
                    
                bid_depth = sum(float(b.get('size', 0)) for b in bids)
                ask_depth = sum(float(a.get('size', 0)) for a in asks)
                imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth + 1e-9)

                tick = MarketTick(
                    source="POLYMARKET",
                    symbol=asset_id,
                    market_id=asset_id,
                    event_timestamp=req_start,
                    received_timestamp=req_end,
                    price=price,
                    bid=best_bid,
                    ask=best_ask,
                    spread=spread,
                    volume=0.0,
                    liquidity=bid_depth + ask_depth,
                    imbalance=imbalance,
                    bid_depth=bid_depth,
                    ask_depth=ask_depth
                )
                
                results.append(tick)
                
                for cb in self.callbacks:
                    await cb(tick)
                    
        return results

    def check_stale(self):
        if not self.last_update:
            self.is_stale = True
        elif (datetime.utcnow() - self.last_update).total_seconds() * 1000 > settings.data_stale_threshold_ms:
            self.is_stale = True
        else:
            self.is_stale = False
        return self.is_stale
