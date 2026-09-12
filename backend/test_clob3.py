import asyncio
import aiohttp

async def test():
    async with aiohttp.ClientSession() as s:
        async with s.get('https://clob.polymarket.com/markets') as r:
            res = await r.json()
            markets = res.get('data', [])
        
        for m in markets[:5]:
            print(f"ID: {m.get('condition_id')} | Active: {m.get('active')} | Closed: {m.get('closed')} | EnableOrderBook: {m.get('enable_order_book')} | Question: {m.get('question')}")
                    
asyncio.run(test())
