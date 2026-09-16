from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Market, MarketSnapshot
from app.api.security import get_current_user

router = APIRouter()

@router.get("")
def get_markets(skip: int = 0, limit: int = 50, active_only: bool = True, db: Session = Depends(get_db)):
    query = db.query(Market)
    if active_only:
        query = query.filter(Market.active == True)
        
    markets = query.order_by(Market.last_update.desc()).offset(skip).limit(limit).all()
    total = query.count()
    
    return {
        "total": total,
        "markets": markets
    }

@router.get("/orderbook/{market_id}")
def get_orderbook(market_id: str, db: Session = Depends(get_db)):
    """Return the latest real CLOB orderbook data for a specific market."""
    market = db.query(Market).filter(
        (Market.market_id == market_id) | (Market.condition_id == market_id)
    ).first()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    
    # Get the most recent snapshot for this market
    snapshot = db.query(MarketSnapshot).filter(
        MarketSnapshot.market_id == market.market_id
    ).order_by(MarketSnapshot.received_timestamp.desc()).first()
    
    if not snapshot:
        return {
            "market_id": market.market_id,
            "question": market.question,
            "status": "NO_DATA",
            "message": "No orderbook snapshots available for this market",
            "best_bid": None,
            "bid_size": None,
            "best_ask": None,
            "ask_size": None,
            "spread": None,
            "spread_pct": None,
            "bid_depth": None,
            "ask_depth": None,
            "liquidity_status": "UNAVAILABLE",
            "timestamp": None,
        }
    
    best_bid = snapshot.bid
    best_ask = snapshot.ask
    spread = snapshot.spread
    bid_depth = snapshot.bid_depth
    ask_depth = snapshot.ask_depth
    
    spread_pct = (spread / best_ask * 100) if best_ask and best_ask > 0 and spread else None
    
    total_depth = (bid_depth or 0) + (ask_depth or 0)
    if total_depth >= 1000:
        liquidity_status = "HIGH"
    elif total_depth >= 100:
        liquidity_status = "MEDIUM"
    elif total_depth > 0:
        liquidity_status = "LOW"
    else:
        liquidity_status = "EMPTY"
    
    return {
        "market_id": market.market_id,
        "question": market.question,
        "status": "LIVE",
        "best_bid": best_bid,
        "bid_size": bid_depth,
        "best_ask": best_ask,
        "ask_size": ask_depth,
        "spread": spread,
        "spread_pct": round(spread_pct, 4) if spread_pct else None,
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
        "imbalance": snapshot.imbalance,
        "volume": snapshot.volume,
        "liquidity": snapshot.liquidity,
        "liquidity_status": liquidity_status,
        "price": snapshot.price,
        "timestamp": snapshot.received_timestamp,
        "latency_ms": snapshot.latency_ms,
        "trade_eligible": snapshot.trade_eligible,
        "ineligibility_reason": snapshot.ineligibility_reason,
    }

@router.get("/{market_id}")
def get_market_detail(market_id: str, db: Session = Depends(get_db)):
    market = db.query(Market).filter((Market.market_id == market_id) | (Market.condition_id == market_id)).first()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
        
    snapshot = db.query(MarketSnapshot).filter(MarketSnapshot.market_id == market.market_id).order_by(MarketSnapshot.received_timestamp.desc()).first()
    
    return {
        "market": market,
        "latest_snapshot": snapshot
    }
