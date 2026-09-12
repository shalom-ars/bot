from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class MarketTick(BaseModel):
    source: str
    symbol: str
    market_id: str
    event_timestamp: datetime
    received_timestamp: datetime
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    volume: Optional[float] = None
    liquidity: Optional[float] = None
    imbalance: Optional[float] = None
    bid_depth: Optional[float] = None
    ask_depth: Optional[float] = None
    
    @property
    def latency_ms(self) -> int:
        return int((self.received_timestamp - self.event_timestamp).total_seconds() * 1000)
