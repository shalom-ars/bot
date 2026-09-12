import asyncio
from app.connectors.polymarket import PolymarketConnector

async def debug_tokens():
    poly = PolymarketConnector()
    print("Fetching active markets...")
    markets = await poly.get_active_markets(limit=20)
    print(f"Total discovered: {len(markets)}")
    
    import json
    for m in markets:
        clob_str = m.get('clobTokenIds', '[]')
        try:
            tokens = json.loads(clob_str)
        except:
            tokens = []
            
        print(f"\nMarket ID: {m.get('id')} - {m.get('question')}")
        print(f"clobTokenIds raw: {clob_str}")
        print(f"parsed tokens: {tokens}")
        print(f"token ID length: {len(tokens[0]) if tokens else 0}")
        print(f"token ID type: {type(tokens[0]).__name__ if tokens else 'N/A'}")
        
        if tokens:
            token_id = tokens[0]
            print(f"Testing /book GET for token {token_id}...")
            url = f"{poly.clob_api_url}/book?token_id={token_id}"
            
            async with poly.session.get(url) as resp:
                status = resp.status
                body = await resp.text()
                print(f"Status: {status}")
                if status != 200:
                    print(f"Response: {body[:200]}")
                else:
                    print(f"Success! Body length: {len(body)}")
                    
            print(f"Testing /books POST for token {token_id}...")
            post_url = f"{poly.clob_api_url}/books"
            payload = [{"token_id": token_id}]
            async with poly.session.post(post_url, json=payload) as resp:
                post_status = resp.status
                post_body = await resp.text()
                print(f"POST Status: {post_status}")
                if post_status != 200:
                    print(f"POST Response: {post_body[:200]}")
                else:
                    print(f"POST Success! Body length: {len(post_body)}")
            break

    await poly.disconnect()

if __name__ == "__main__":
    asyncio.run(debug_tokens())
