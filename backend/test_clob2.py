import asyncio
import aiohttp

async def test():
    async with aiohttp.ClientSession() as s:
        # Fetch clob markets where enable_order_book is true and active is true
        print("Fetching CLOB markets...")
        async with s.get('https://clob.polymarket.com/markets?active=true') as r:
            res = await r.json()
            markets = res.get('data', [])
            
        print(f"Total CLOB markets returned: {len(markets)}")
        active_clobs = [m for m in markets if m.get('enable_order_book') and m.get('active')]
        print(f"Active CLOB markets: {len(active_clobs)}")
        
        if active_clobs:
            first = active_clobs[0]
            token_id = first.get('tokens', [{}])[0].get('token_id')
            print(f"Testing token_id {token_id} for {first.get('question')} ...")
            async with s.get(f'https://clob.polymarket.com/book?token_id={token_id}') as br:
                print("Status:", br.status)
                if br.status == 200:
                    data = await br.json()
                    print(f"Got orderbook! Bids: {len(data.get('bids', []))} Asks: {len(data.get('asks', []))}")
                else:
                    print(await br.text())
                    
asyncio.run(test())
