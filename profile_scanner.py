import asyncio
import time
import json
from app.engine.scanner import MarketScanner
from app.db.session import SessionLocal

async def main():
    scanner = MarketScanner()
    await scanner.start()
    
    print("Running a single scanner cycle to measure BEFORE performance...")
    
    start = time.time()
    
    active_markets = await asyncio.to_thread(scanner._sync_get_active_market_ids)
    print(f"Tracking {len(active_markets)} active markets")
    
    valid_asset_ids = set()
    
    for i in range(0, min(len(active_markets), 200), 50): # Limiting to 200 for profiling
        chunk = active_markets[i:i+50]
        t1 = time.time()
        ticks = await scanner.poly.fetch_markets_books(chunk)
        t2 = time.time()
        print(f"Fetched {len(chunk)} orderbooks in {t2-t1:.2f}s")
        for t in ticks:
            valid_asset_ids.add(t.market_id)
        
    end = time.time()
    
    duration = end - start
    
    print(f"Cycle Duration for 200 markets: {duration:.2f} seconds")
    
    await scanner.stop()

if __name__ == "__main__":
    asyncio.run(main())
