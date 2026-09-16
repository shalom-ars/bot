from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Signal, Market
from app.api.security import get_current_user

router = APIRouter()

@router.get("")
def get_signals(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    signals = db.query(Signal).order_by(Signal.timestamp.desc()).offset(skip).limit(limit).all()
    total = db.query(Signal).count()
    
    # Enrich each signal with market question
    enriched = []
    for s in signals:
        market = db.query(Market).filter(Market.market_id == s.market_id).first()
        enriched.append({
            "id": s.id,
            "timestamp": s.timestamp,
            "market_id": s.market_id,
            "market_question": market.question if market else "Unknown Market",
            "signal_type": s.signal_type,
            "strategy": s.strategy,
            "fair_probability": s.fair_probability,
            "calibrated_probability": s.calibrated_probability,
            "market_prob": s.market_prob,
            "model_prob": s.model_prob,
            "entry_price": s.entry_price,
            "raw_edge": s.raw_edge,
            "spread_cost": s.spread_cost,
            "slippage_cost": s.slippage_cost,
            "liquidity_cost": s.liquidity_cost,
            "fees": s.fees,
            "net_edge": s.net_edge,
            "effective_edge": s.effective_edge,
            "threshold": s.threshold,
            "confidence": s.confidence,
            "uncertainty": s.uncertainty,
            "correlation_status": s.correlation_status,
            "market_quality_status": s.market_quality_status,
            "model_version": s.model_version,
            "reason": s.reason,
        })
    
    return {
        "total": total,
        "signals": enriched
    }
