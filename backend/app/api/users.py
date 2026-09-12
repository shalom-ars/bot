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
        # Honest state: Return a 0 portfolio instead of 404 for new users
        return {
            "initial_balance": 500.0,
            "current_balance": 500.0,
            "equity": 500.0,
            "exposure": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "drawdown": 0.0,
            "trades": 0,
            "wins": 0
        }
    return portfolio

@router.get("/positions")
def get_user_positions(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    positions = db.query(UserPosition).filter(UserPosition.user_id == current_user.id).offset(skip).limit(limit).all()
    total = db.query(UserPosition).filter(UserPosition.user_id == current_user.id).count()
    return {"total": total, "positions": positions}

@router.get("/trades")
def get_user_trades(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    trades = db.query(UserTrade).filter(UserTrade.user_id == current_user.id).offset(skip).limit(limit).all()
    total = db.query(UserTrade).filter(UserTrade.user_id == current_user.id).count()
    return {"total": total, "trades": trades}

@router.get("/performance")
def get_user_performance(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    portfolio = db.query(UserPortfolio).filter(UserPortfolio.user_id == current_user.id).first()
    if not portfolio or portfolio.trades == 0:
        return {"win_rate": 0, "profit_factor": 0, "roi": 0, "trades": 0, "wins": 0, "losses": 0}
    
    losses = portfolio.trades - portfolio.wins
    win_rate = (portfolio.wins / portfolio.trades) * 100 if portfolio.trades > 0 else 0
    roi = ((portfolio.equity - portfolio.initial_balance) / portfolio.initial_balance) * 100
    
    return {
        "win_rate": round(win_rate, 2),
        "roi": round(roi, 2),
        "trades": portfolio.trades,
        "wins": portfolio.wins,
        "losses": losses
    }

@router.get("/risk")
def get_user_risk(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    settings = db.query(UserSetting).filter(UserSetting.user_id == current_user.id).first()
    portfolio = db.query(UserPortfolio).filter(UserPortfolio.user_id == current_user.id).first()
    
    max_risk = settings.max_position_risk if settings else 0.02
    exposure = portfolio.exposure if portfolio else 0.0
    equity = portfolio.equity if portfolio else 500.0
    
    return {
        "max_position_risk": max_risk,
        "current_exposure": exposure,
        "exposure_percent": round((exposure / equity) * 100, 2) if equity > 0 else 0,
        "status": "SAFE" if (exposure / equity) < max_risk else "WARNING"
    }

@router.get("/settings")
def get_user_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    settings = db.query(UserSetting).filter(UserSetting.user_id == current_user.id).first()
    return settings

@router.get("/subscription")
def get_user_subscription(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    return sub
