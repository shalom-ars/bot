import asyncio
import random
from datetime import datetime
from app.db.schemas import MarketTick

class MockDataConnector:
    def __init__(self):
        self.running = False
        self.callbacks = []
        self.is_stale = False
        self.last_update = datetime.utcnow()
        self.prices = {
            "POLY_BTC_UP": 0.5,
            "POLY_ETH_UP": 0.5
        }

    def register_callback(self, callback):
        self.callbacks.append(callback)

    async def start(self):
        self.running = True
        while self.running:
            now = datetime.utcnow()
            
            # Simulate Polymarket ticks
            for sym in ["POLY_BTC_UP", "POLY_ETH_UP"]:
                self.prices[sym] = max(0.01, min(0.99, self.prices[sym] + random.uniform(-0.02, 0.02)))
                price = self.prices[sym]
                
                spread = random.uniform(0.005, 0.02)
                best_bid = price - (spread/2)
                best_ask = price + (spread/2)
                bid_depth = random.uniform(100, 10000)
                ask_depth = random.uniform(100, 10000)
                imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)

                tick = MarketTick(
                    # P1-004 FIX: source must be "POLYMARKET" to pass snapshot_validator
                    # mock mode is disabled by default (data_mode=live) but when enabled
                    # it must not be silently rejected at the validator
                    source="POLYMARKET",
                    symbol=sym,
                    market_id=sym,
                    event_timestamp=now,
                    received_timestamp=now,
                    price=price,
                    bid=best_bid,
                    ask=best_ask,
                    spread=spread,
                    volume=random.uniform(0, 100),
                    liquidity=bid_depth + ask_depth,
                    imbalance=imbalance,
                    bid_depth=bid_depth,
                    ask_depth=ask_depth
                )
                
                for cb in self.callbacks:
                    await cb(tick)
                    
            self.last_update = datetime.utcnow()
            await asyncio.sleep(1)

    def check_stale(self):
        return False

    async def stop(self):
        self.running = False
