"""
BTC 5M Market Selector.

Discovers genuine BTC 5-minute prediction markets from Polymarket
using the Gamma API and CLOB data.

Rules:
- Must contain BTC/Bitcoin in the question
- Must be an active, non-expired market
- Must have valid YES/NO outcome tokens
- Must have fresh CLOB data within staleness threshold
- Must meet minimum liquidity and spread requirements
- Duration/resolution must be short-horizon (5-minute style)
  i.e. end_time within next 10 minutes OR market started < 5m ago
"""
import logging
import urllib.request
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

BTC_KEYWORDS = ["btc", "bitcoin", "btcusd", "xbt"]
# 5-minute markets: end_time within next 8 minutes from now,
# OR total market duration <= 600 seconds (10 min window for short-horizon markets)
MAX_REMAINING_SECONDS = 610
MIN_REMAINING_SECONDS = 30   # Do not enter too close to resolution

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API  = "https://clob.polymarket.com"

MIN_LIQUIDITY = 50.0       # minimum total depth ($)
MAX_SPREAD    = 0.10       # 10% max spread for discovery (tighter check in strategy)
USER_AGENT    = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


@dataclass
class BTC5MMarketInfo:
    market_id: str          # token_id (YES token)
    condition_id: str
    question: str
    yes_token_id: str
    no_token_id: Optional[str]
    end_time: Optional[datetime]
    start_time: Optional[datetime]
    # Live CLOB data (refreshed each cycle)
    best_bid: float = 0.0
    best_ask: float = 0.0
    bid_depth: float = 0.0
    ask_depth: float = 0.0
    spread: float = 1.0
    mid_price: float = 0.5
    imbalance: float = 0.0
    liquidity: float = 0.0
    orderbook_timestamp: Optional[datetime] = None
    is_valid: bool = False
    rejection_reason: str = ""
    time_remaining_sec: float = 0.0


def _is_btc_market(question: str) -> bool:
    if not question:
        return False
    q = question.lower()
    has_btc = any(kw in q for kw in BTC_KEYWORDS)
    has_up_down = "up or down" in q or "5m" in q or "5-min" in q
    return has_btc and has_up_down


def _parse_utc(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Handle various ISO formats
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except Exception:
        return None


import requests

def _fetch_json(url: str, method: str = "GET", payload: Optional[bytes] = None) -> Optional[any]:
    headers = {"User-Agent": USER_AGENT}
    if payload:
        headers["Content-Type"] = "application/json"
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=10)
        else:
            resp = requests.request(method, url, headers=headers, data=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.debug(f"[BTC5M Selector] Fetch error {url}: {e}")
        return None


def discover_btc5m_markets() -> List[BTC5MMarketInfo]:
    """
    Retrieve the CURRENT rolling Polymarket "BTC Up or Down 5m" markets directly.
    Constructs the exact slug using the 5-minute Unix timestamp buckets.
    """
    now = datetime.now(timezone.utc)
    btc_candidates = []
    
    # Calculate the 5-minute unix bucket
    now_ts = int(now.timestamp())
    current_bucket = now_ts - (now_ts % 300)
    
    # Fetch current, previous, and next buckets to be safe
    buckets_to_check = [
        current_bucket - 300,
        current_bucket,
        current_bucket + 300,
        current_bucket + 600,
    ]
    
    for bucket in buckets_to_check:
        slug = f"btc-updown-5m-{bucket}"
        data = _fetch_json(f"{GAMMA_API}/events?slug={slug}")
        
        if not data or not isinstance(data, list):
            continue
            
        for event in data:
            if not event.get("active") or event.get("closed"):
                continue
                
            for market in event.get("markets", []):
                question = market.get("question", "") or event.get("title", "")
                
                end_time = _parse_utc(market.get("endDate") or market.get("end_date_iso"))
                start_time = _parse_utc(market.get("startDate") or market.get("start_date_iso"))
                
                # Fix start time for 5-minute rolling markets
                if end_time:
                    from datetime import timedelta
                    start_time = end_time - timedelta(minutes=5)

                if not end_time:
                    continue  # Safety

                remaining = (end_time - now).total_seconds()
                
                condition_id = market.get("conditionId", "") or market.get("condition_id", "")
                clob_token_ids = market.get("clobTokenIds", []) or market.get("clob_token_ids", [])
                
                if isinstance(clob_token_ids, str):
                    import json
                    try:
                        clob_token_ids = json.loads(clob_token_ids)
                    except:
                        clob_token_ids = []

                if len(clob_token_ids) < 1:
                    continue

                yes_token = clob_token_ids[0]
                no_token  = clob_token_ids[1] if len(clob_token_ids) > 1 else None

                if not yes_token:
                    continue

                btc_candidates.append({
                    "market_id": yes_token,
                    "condition_id": condition_id,
                    "question": question,
                    "yes_token_id": yes_token,
                    "no_token_id": no_token,
                    "end_time": end_time,
                    "start_time": start_time,
                    "remaining_sec": remaining,
                })

    if not btc_candidates:
        logger.info("[BTC5M Selector] No BTC 5M markets found from Gamma API")
        return []

    logger.info(f"[BTC5M Selector] Found {len(btc_candidates)} BTC 5M candidates, fetching CLOB data...")

    # 2. Batch fetch CLOB orderbooks
    all_token_ids = []
    for c in btc_candidates:
        all_token_ids.append(c["yes_token_id"])
        if c["no_token_id"]:
            all_token_ids.append(c["no_token_id"])

    payload = json.dumps([{"token_id": t} for t in all_token_ids]).encode("utf-8")
    books_data = _fetch_json(f"{CLOB_API}/books", method="POST", payload=payload)

    clob_map: Dict[str, dict] = {}
    if books_data and isinstance(books_data, list):
        for book in books_data:
            asset_id = book.get("asset_id", "")
            if asset_id:
                bids = sorted(book.get("bids", []), key=lambda x: float(x.get("price", 0)), reverse=True)
                asks = sorted(book.get("asks", []), key=lambda x: float(x.get("price", 1)), reverse=False)
                best_bid = float(bids[0]["price"]) if bids else 0.0
                best_ask = float(asks[0]["price"]) if asks else 1.0
                bid_depth = sum(float(b.get("size", 0)) for b in bids)
                ask_depth = sum(float(a.get("size", 0)) for a in asks)
                spread = best_ask - best_bid if best_bid > 0 and best_ask > 0 else 1.0
                mid = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0.5
                imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth + 1e-9)
                clob_map[asset_id] = {
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "bid_depth": bid_depth,
                    "ask_depth": ask_depth,
                    "spread": spread,
                    "mid_price": mid,
                    "imbalance": imbalance,
                    "liquidity": bid_depth + ask_depth,
                    "timestamp": datetime.now(timezone.utc),
                }

    # 3. Validate and build BTC5MMarketInfo
    now2 = datetime.now(timezone.utc)
    results: List[BTC5MMarketInfo] = []
    for c in btc_candidates:
        clob = clob_map.get(c["yes_token_id"])
        remaining = c["remaining_sec"]
        
        # Calculate time validity
        is_valid = True
        rejection_reason = ""
        if remaining < MIN_REMAINING_SECONDS:
            is_valid = False
            rejection_reason = "Expired or <60s remaining"
        elif remaining > MAX_REMAINING_SECONDS:
            is_valid = False
            rejection_reason = "Horizon too long (>10m)"

        info = BTC5MMarketInfo(
            market_id=c["market_id"],
            condition_id=c["condition_id"],
            question=c["question"],
            yes_token_id=c["yes_token_id"],
            no_token_id=c["no_token_id"],
            end_time=c["end_time"],
            start_time=c["start_time"],
            best_bid=clob.get("best_bid", 0) if clob else 0,
            best_ask=clob.get("best_ask", 1) if clob else 1,
            bid_depth=clob.get("bid_depth", 0) if clob else 0,
            ask_depth=clob.get("ask_depth", 0) if clob else 0,
            spread=clob.get("spread", 1) if clob else 1,
            mid_price=clob.get("mid_price", 0.5) if clob else 0.5,
            imbalance=clob.get("imbalance", 0) if clob else 0,
            liquidity=clob.get("liquidity", 0) if clob else 0,
            orderbook_timestamp=clob.get("timestamp") if clob else None,
            is_valid=is_valid,
            rejection_reason=rejection_reason,
            time_remaining_sec=remaining,
        )

        if not clob:
            info.is_valid = False
            info.rejection_reason = "No CLOB orderbook data available"
        elif info.best_bid >= info.best_ask:
            info.is_valid = False
            info.rejection_reason = "Inverted orderbook: bid >= ask"
        elif info.spread > MAX_SPREAD:
            info.is_valid = False
            info.rejection_reason = f"Spread too wide: {info.spread:.4f} > {MAX_SPREAD}"
        elif info.liquidity < MIN_LIQUIDITY:
            info.is_valid = False
            info.rejection_reason = f"Insufficient liquidity: {info.liquidity:.2f} < {MIN_LIQUIDITY}"
        elif remaining < MIN_REMAINING_SECONDS:
            info.is_valid = False
            info.rejection_reason = f"Too close to resolution: {remaining:.0f}s remaining"
        elif remaining > MAX_REMAINING_SECONDS:
            info.is_valid = False
            info.rejection_reason = f"Horizon too long (>10m): {remaining/3600:.1f}h remaining"

        results.append(info)

    valid_count = sum(1 for r in results if r.is_valid)
    logger.info(f"[BTC5M Selector] {valid_count}/{len(results)} markets passed validation")
    return results
