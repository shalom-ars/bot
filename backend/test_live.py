import sys
import asyncio
from datetime import datetime, timezone
import json
sys.path.append('.')

from app.btc5m.engine import discover_btc5m_markets
from app.btc5m.strategy import BTC5MStrategy

async def live_test():
    markets = discover_btc5m_markets()
    valid = [m for m in markets if m.is_valid]
    if not valid:
        print("No valid active BTC5M market right now.")
        return
        
    market = valid[0]
    
    import httpx
    try:
        resp = httpx.post(
            "https://polygon-bor-rpc.publicnode.com",
            json={"jsonrpc": "2.0", "method": "eth_call", "params": [{"to": "0xc907E116054Ad103354f2D350FD2514433D57F6f", "data": "0x50d25bcd"}, "latest"], "id": 1}
        )
        hex_answer = resp.json()["result"]
        btc_price = int(hex_answer, 16) / 100000000.0
    except Exception:
        btc_price = 76000.0
        
    p2b = None
    start_ts = int(market.start_time.replace(tzinfo=timezone.utc).timestamp())
    slug = f"btc-updown-5m-{start_ts - 300}"
    resp = httpx.get(f"https://gamma-api.polymarket.com/events?slug={slug}")
    events = resp.json()
    if events and len(events) > 0 and "eventMetadata" in events[0]:
        p2b = events[0]["eventMetadata"].get("finalPrice")
        if p2b: p2b = float(p2b)
        
    resp_ob = httpx.get(f"https://clob.polymarket.com/book?token_id={market.yes_token_id}")
    ob = resp_ob.json()
    
    best_bid = float(ob.get("bids", [{"price":0.5}])[0]["price"])
    best_ask = float(ob.get("asks", [{"price":0.5}])[0]["price"])
    
    features = {
        'time_remaining_sec': 120.0,
        'mid_price': (best_bid+best_ask)/2,
        'bid': best_bid,
        'ask': best_ask,
        'spread': best_ask - best_bid,
        'bid_depth': 10000,
        'ask_depth': 10000,
        'rolling_volatility': 0.01,
        'short_momentum_1m': 0.0,
        'bid_ask_imbalance': 0.0,
        'return_1': 0.0
    }
    
    strat = BTC5MStrategy()
    sig = strat.evaluate(
        market_id=market.market_id, condition_id=market.condition_id, question=market.question,
        yes_token_id=market.yes_token_id, no_token_id=market.no_token_id,
        features=features, orderbook_timestamp=datetime.now(timezone.utc),
        btc_price=btc_price, price_to_beat=p2b, current_balance=500.0
    )
    
    print("========================================")
    print("2. REAL ACTIVE BTC5M MARKET TEST")
    print("========================================")
    print(f"market: {market.question}")
    print(f"YES token ID: {market.yes_token_id}")
    print(f"NO token ID: {market.no_token_id}")
    print(f"YES bid/ask: {features.get('bid',0)} / {features.get('ask',0)}")
    print(f"NO bid/ask: {round(1-features.get('ask',0), 2)} / {round(1-features.get('bid',0), 2)}")
    
    selected_side = "YES" if sig.yes_score >= sig.no_score else "NO"
    print(f"selected side: {selected_side}")
    print(f"execution side: {sig.side}")
    print(f"entry price: {sig.entry_price}")
    qty = sig.position_size / sig.entry_price if sig.entry_price else 0
    print(f"quantity: {qty}")
    print(f"planned risk: {sig.planned_risk}")
    print(f"planned reward: {sig.planned_reward}")
    print(f"planned R:R: {sig.planned_rr}")
    print(f"P&L calculation if Win: {qty - sig.position_size}")
    print(f"P&L calculation if Loss: {-sig.position_size}")
    print("========================================")

asyncio.run(live_test())
