from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, UserPortfolio, UserTrade, UserSetting, Subscription, UserPosition, Market
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
    
    # Enrich each position with market question
    enriched = []
    for p in positions:
        market = db.query(Market).filter(Market.market_id == p.market_id).first()
        enriched.append({
            "id": p.id,
            "user_id": p.user_id,
            "market_id": p.market_id,
            "condition_id": p.condition_id,
            "token_id": p.token_id,
            "side": p.side,
            "entry_price": p.entry_price,
            "quantity": p.quantity,
            "market_question": market.question if market else "Unknown Market",
            "current_price": market.current_price if market else p.entry_price,
            "best_bid": market.best_bid if market else None,
            "best_ask": market.best_ask if market else None,
            "spread": market.spread if market else None,
        })
    
    return {"total": total, "positions": enriched}

@router.get("/trades")
def get_user_trades(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    trades = db.query(UserTrade).filter(UserTrade.user_id == current_user.id).order_by(UserTrade.entry_time.desc()).offset(skip).limit(limit).all()
    total = db.query(UserTrade).filter(UserTrade.user_id == current_user.id).count()
    
    # Enrich each trade with market question
    enriched = []
    for t in trades:
        market = db.query(Market).filter(Market.market_id == t.market_id).first()
        enriched.append({
            "id": t.id,
            "user_id": t.user_id,
            "market_id": t.market_id,
            "condition_id": t.condition_id,
            "token_id": t.token_id,
            "side": t.side,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "quantity": t.quantity,
            "pnl": t.pnl,
            "status": t.status,
            "entry_time": t.entry_time,
            "exit_time": t.exit_time,
            "market_question": market.question if market else "Unknown Market",
        })
    
    return {"total": total, "trades": enriched}

@router.get("/performance")
def get_user_performance(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    portfolio = db.query(UserPortfolio).filter(UserPortfolio.user_id == current_user.id).first()
    if not portfolio:
        return {"win_rate": 0, "profit_factor": 0, "roi": 0, "trades": 0, "closed_trades": 0, "wins": 0, "losses": 0}
    
    # Calculate performance from actual trades
    all_trades = db.query(UserTrade).filter(UserTrade.user_id == current_user.id).all()
    total_trades = len(all_trades)
    
    closed_trades = [t for t in all_trades if t.status == 'CLOSED']
    wins = len([t for t in closed_trades if (t.pnl or 0) > 0])
    losses = len([t for t in closed_trades if (t.pnl or 0) < 0])
    
    win_rate = (wins / len(closed_trades)) * 100 if closed_trades else 0
    roi = ((portfolio.equity - portfolio.initial_balance) / portfolio.initial_balance) * 100 if portfolio.initial_balance else 0
    
    return {
        "win_rate": round(win_rate, 2),
        "roi": round(roi, 2),
        "trades": total_trades,
        "closed_trades": len(closed_trades),
        "wins": wins,
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
