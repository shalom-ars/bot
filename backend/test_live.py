import asyncio
import json
from app.connectors.polymarket import PolymarketConnector

async def test():
    print("Testing Live Connection to Polymarket...")
    poly = PolymarketConnector()
    markets = await poly.get_active_markets(limit=20)
    print(f"Discovered {len(markets)} active markets total.")
    active_m = [m for m in markets if m.get('active', False) and not m.get('closed', True)]
    
    if len(active_m) > 0:
        for m in active_m:
            try:
                tokens = json.loads(m.get('clobTokenIds', '[]'))
                if len(tokens) > 0:
                    token_id = tokens[0]
                    print(f"Fetching orderbook data for token: {token_id} ({m.get('question')})")
                    price = await poly.fetch_market_data(token_id)
                    print(f"Current Mid Price: {price}")
                    break
            except Exception as e:
                print(e)
    else:
        print("No active open markets found to test.")
        
    await poly.disconnect()
    print("Done")

if __name__ == "__main__":
    asyncio.run(test())
