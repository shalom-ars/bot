import asyncio
from app.connectors.polymarket import PolymarketConnector

async def test():
    poly = PolymarketConnector()
    markets = await poly.get_active_markets(limit=2)
    print(markets)
    await poly.disconnect()

asyncio.run(test())
