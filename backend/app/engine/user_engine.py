import logging
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import User, UserPortfolio, UserSetting, UserTrade, UserPosition
from datetime import datetime

logger = logging.getLogger(__name__)

def execute_saas_user_trades(signal_data: dict, market_info: dict, current_price: float):
    """
    Given a global 'APPROVE' signal from the StrategyRouter, process a virtual paper trade
    for every SaaS user that is active, utilizing their isolated UserPortfolio and UserSetting.
    """
    sig_type = signal_data["signal_type"]
    if sig_type not in ("BUY", "SELL"):
        return

    market_id = signal_data.get("market_id")
    token_id = signal_data.get("token_id")
    
    # We must simulate slippage to match Phase 3 rules
    # Using 1% generic slippage simulation for SaaS paper trades if exact is unknown
    simulated_slippage = 0.01 
    if sig_type == "BUY":
        entry_price = current_price + simulated_slippage
    else:
        entry_price = current_price - simulated_slippage
        
    if entry_price <= 0 or entry_price >= 1:
        return # Cannot execute out of bounds

    db = SessionLocal()
    try:
        users = db.query(User).filter(User.is_active == True).all()
        for user in users:
            portfolio = db.query(UserPortfolio).filter(UserPortfolio.user_id == user.id).first()
            settings = db.query(UserSetting).filter(UserSetting.user_id == user.id).first()
            if not portfolio or not settings:
                continue
                
            # 1. Size position based on user's specific max_position_risk
            risk_amount = portfolio.current_balance * settings.max_position_risk
            quantity = risk_amount / entry_price if entry_price > 0 else 0
            
            if quantity <= 0:
                continue
                
            # 2. Check if portfolio has sufficient funds
            if portfolio.current_balance < risk_amount:
                continue
                
            # 3. Check drawdown (Phase 6 rule adapted for users)
            if portfolio.drawdown > settings.max_drawdown:
                continue

            # 4. Check if position already exists (prevent duplicate buys)
            existing = db.query(UserPosition).filter(
                UserPosition.user_id == user.id,
                UserPosition.market_id == market_id,
                UserPosition.token_id == token_id
            ).first()
            if existing:
                continue
                
            # EXECUTE VIRTUAL TRADE
            # Deduct balance
            portfolio.current_balance -= risk_amount
            portfolio.exposure += risk_amount
            
            # Record Position
            new_position = UserPosition(
                user_id=user.id,
                market_id=market_id,
                condition_id=market_info.get("condition_id"),
                token_id=token_id,
                side=sig_type,
                entry_price=entry_price,
                quantity=quantity
            )
            db.add(new_position)
            
            # Record Trade
            new_trade = UserTrade(
                user_id=user.id,
                market_id=market_id,
                condition_id=market_info.get("condition_id"),
                token_id=token_id,
                side=sig_type,
                entry_price=entry_price,
                quantity=quantity,
                status="OPEN"
            )
            db.add(new_trade)
            
            portfolio.trades += 1
            
        db.commit()
    except Exception as e:
        logger.error(f"SaaS User Execution Error: {e}")
        db.rollback()
    finally:
        db.close()

def resolve_saas_user_trades(market_id: str, resolution: str):
    """
    Close out SaaS user trades when a market resolves.
    resolution: "YES" or "NO" (the actual token outcome, 1.0 or 0.0)
    """
    db = SessionLocal()
    try:
        resolved_price = 1.0 if resolution == "YES" else 0.0
        
        open_positions = db.query(UserPosition).filter(UserPosition.market_id == market_id).all()
        for pos in open_positions:
            user = db.query(UserPortfolio).filter(UserPortfolio.user_id == pos.user_id).first()
            if not user:
                continue
            
            pnl = 0.0
            if pos.side == "BUY_YES" or pos.side == "BUY":
                pnl = (resolved_price - pos.entry_price) * pos.quantity
            elif pos.side == "BUY_NO" or pos.side == "SELL":
                pnl = ((1.0 - resolved_price) - pos.entry_price) * pos.quantity
                
            user.realized_pnl += pnl
            user.current_balance += pnl + (pos.entry_price * pos.quantity)
            user.exposure -= (pos.entry_price * pos.quantity)
            
            trade = db.query(UserTrade).filter(
                UserTrade.user_id == pos.user_id,
                UserTrade.market_id == market_id,
                UserTrade.status == "OPEN"
            ).first()
            
            if trade:
                trade.status = "CLOSED"
                trade.pnl = pnl
                trade.exit_price = resolved_price
                
            db.delete(pos)
            
        db.commit()
    except Exception as e:
        logger.error(f"Failed to resolve SaaS user trades: {e}")
        db.rollback()
    finally:
        db.close()
