import asyncio
import aiohttp

async def test():
    async with aiohttp.ClientSession() as s:
        # Let's hit the /markets endpoint to get a valid clob token
        async with s.get('https://clob.polymarket.com/markets') as r:
            markets = await r.json()
            if markets.get('data'):
                print("Got markets from CLOB API.")
                first = markets['data'][0]
                print(first)
                token_id = first.get('tokens', [{}])[0].get('token_id')
                if token_id:
                    print(f"\nTrying GET /book?token_id={token_id}")
                    async with s.get(f'https://clob.polymarket.com/book?token_id={token_id}') as br:
                        print("Status:", br.status)
                        print(await br.text())

asyncio.run(test())
