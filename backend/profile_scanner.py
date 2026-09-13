import asyncio
import time
import json
import os
from app.engine.scanner import Orchestrator
from app.db.session import SessionLocal

async def main():
    scanner = Orchestrator()
    # Don't start the background loops, just test the functions
    
    print("Measuring performance...")
    
    start = time.time()
    
    active_markets = await asyncio.to_thread(scanner._sync_get_active_market_ids)
    print(f"Tracking {len(active_markets)} active markets")
    
    valid_asset_ids = set()
    
    for i in range(0, min(len(active_markets), 200), 50): # Limiting to 200 for profiling
        chunk = active_markets[i:i+50]
        t1 = time.time()
        ticks = await scanner.poly.fetch_markets_books(chunk)
        t2 = time.time()
        print(f"Fetched {len(ticks)} orderbooks in {t2-t1:.2f}s")
        
        # Batch process
        t3 = time.time()
        await asyncio.to_thread(scanner._sync_handle_ticks_batch, ticks, time.time())
        t4 = time.time()
        print(f"Batch processed {len(ticks)} in {t4-t3:.2f}s")
        
    end = time.time()
    duration = end - start
    print(f"Cycle Duration for 200 markets: {duration:.2f} seconds")
    
if __name__ == "__main__":
    asyncio.run(main())
