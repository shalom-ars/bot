import asyncio
import aiohttp
import json

async def test():
    async with aiohttp.ClientSession() as s:
        print("Fetching active markets from Gamma...")
        async with s.get('https://gamma-api.polymarket.com/events?limit=20&active=true&closed=false') as r:
            events = await r.json()
        
        all_tokens = []
        for e in events:
            for m in e.get('markets', []):
                clob_str = m.get('clobTokenIds', '[]')
                try:
                    tokens = json.loads(clob_str)
                    if tokens:
                        all_tokens.append(tokens[0])
                except:
                    pass
                    
        print(f"Extracted {len(all_tokens)} token IDs. Testing POST /books...")
        
        # Batch test first 10
        batch = [{"token_id": t} for t in all_tokens[:10]]
        async with s.post('https://clob.polymarket.com/books', json=batch) as r:
            print("Status:", r.status)
            res = await r.json()
            if isinstance(res, list):
                print(f"Received {len(res)} results in batch.")
                if res:
                    print("Keys:", res[0].keys())
                    print("Asset ID / token?:", res[0].get('asset_id'), res[0].get('token'))
            else:
                print(res)

asyncio.run(test())
