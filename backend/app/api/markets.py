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
