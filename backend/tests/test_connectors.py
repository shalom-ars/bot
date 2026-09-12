import pytest
import asyncio
from datetime import datetime, timedelta
from app.config import settings
from app.connectors.polymarket import PolymarketConnector

@pytest.mark.asyncio
async def test_polymarket_stale_logic():
    connector = PolymarketConnector()
    assert connector.check_stale() == True
    
    connector.last_update = datetime.utcnow()
    assert connector.check_stale() == False
    
    # Simulate old update
    connector.last_update = datetime.utcnow() - timedelta(milliseconds=settings.data_stale_threshold_ms + 100)
    assert connector.check_stale() == True
