from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, UserPortfolio, UserTrade, UserSetting, Subscription
from app.api.security import get_current_user

router = APIRouter()

@router.get("/me")
def get_user_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "created_at": current_user.created_at
    }

@router.get("/portfolio")
def get_user_portfolio(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    portfolio = db.query(UserPortfolio).filter(UserPortfolio.user_id == current_user.id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio

@router.get("/trades")
def get_user_trades(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Data Isolation: User can ONLY see their own trades.
    trades = db.query(UserTrade).filter(UserTrade.user_id == current_user.id).offset(skip).limit(limit).all()
    total = db.query(UserTrade).filter(UserTrade.user_id == current_user.id).count()
    return {
        "total": total,
        "trades": trades
    }

@router.get("/settings")
def get_user_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    settings = db.query(UserSetting).filter(UserSetting.user_id == current_user.id).first()
    return settings

@router.get("/subscription")
def get_user_subscription(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    return sub
