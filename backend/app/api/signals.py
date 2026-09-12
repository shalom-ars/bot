from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Signal
from app.api.security import get_current_user

router = APIRouter()

@router.get("")
def get_signals(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    signals = db.query(Signal).order_by(Signal.timestamp.desc()).offset(skip).limit(limit).all()
    total = db.query(Signal).count()
    return {
        "total": total,
        "signals": signals
    }
