import uuid
import logging
from datetime import datetime
from app.db.session import SessionLocal
from app.db.models import UserPortfolio, UserSetting, UserTrade, UserPosition
from app.config import settings

logger = logging.getLogger(__name__)

class MultiTenantPaperEngine:
    """
    Executes paper trades for all active SaaS users simultaneously
    based on the same signal, while respecting individual user risk limits.
    """
    
    def execute(self, signal_data: dict, market_info: dict) -> bool:
        if settings.execution_mode != "paper":
            return False
            
        market_id = signal_data['market_id']
        condition_id = market_info.get('condition_id', market_id)
        token_id = market_id
        signal = signal_data['signal_type']
        
        # We must use simulated entry_price instead of mid price
        entry_price = signal_data.get('entry_price', signal_data.get('market_prob', 0.5))
        slippage = signal_data.get('slippage_cost', 0.0)
        fees = signal_data.get('fees', 0.0)
        execution_price = entry_price + slippage + fees
        
        if execution_price <= 0:
            return False

        db = SessionLocal()
        try:
            active_users = db.query(UserPortfolio).filter(UserPortfolio.paper_status == "RUNNING").all()
            executed_count = 0
            
            for portfolio in active_users:
                user_id = portfolio.user_id
                
                # Check user settings
                user_settings = db.query(UserSetting).filter(UserSetting.user_id == user_id).first()
                max_risk = user_settings.max_position_risk if user_settings else 0.05
                
                # Risk check
                if portfolio.exposure / portfolio.equity >= max_risk:
                    continue # Risk limit exceeded
                    
                size = portfolio.equity * max_risk
                
                # Avoid exceeding available balance (simulated margin)
                available_balance = portfolio.current_balance
                if size > available_balance:
                    size = available_balance
                    
                if size < 5.0: # Minimum trade size
                    continue
                    
                quantity = size / execution_price
                
                # Create user trade
                trade = UserTrade(
                    user_id=user_id,
                    market_id=market_id,
                    condition_id=condition_id,
                    token_id=token_id,
                    side=signal,
                    entry_price=execution_price,
                    quantity=quantity,
                    status="OPEN",
                    entry_time=datetime.utcnow()
                )
                db.add(trade)
                
                # Create user position
                pos = UserPosition(
                    user_id=user_id,
                    market_id=market_id,
                    condition_id=condition_id,
                    token_id=token_id,
                    side=signal,
                    entry_price=execution_price,
                    quantity=quantity
                )
                db.add(pos)
                
                # Update portfolio
                portfolio.current_balance -= size
                portfolio.exposure += size
                portfolio.trades += 1
                
                executed_count += 1
                
            db.commit()
            return executed_count > 0
            
        except Exception as e:
            db.rollback()
            logger.error(f"Multi-tenant paper engine error: {e}")
            return False
        finally:
            db.close()

    def update_positions(self, market_id: str, current_price: float, is_resolved: bool = False, resolved_price: float = 0.0):
        db = SessionLocal()
        try:
            positions = db.query(UserPosition).filter(UserPosition.market_id == market_id).all()
            if not positions:
                return

            for pos in positions:
                portfolio = db.query(UserPortfolio).filter(UserPortfolio.user_id == pos.user_id).first()
                if not portfolio:
                    continue
                    
                if is_resolved:
                    pnl = 0.0
                    if pos.side in ["BUY_YES", "BUY"]:
                        pnl = (resolved_price - pos.entry_price) * pos.quantity
                    elif pos.side in ["BUY_NO", "SELL"]:
                        pnl = ((1.0 - resolved_price) - pos.entry_price) * pos.quantity

                    self._close_user_trade(db, pos.user_id, market_id, resolved_price, pnl)
                    
                    position_cost = pos.entry_price * pos.quantity
                    portfolio.exposure = max(0.0, portfolio.exposure - position_cost)
                    portfolio.current_balance += (position_cost + pnl)
                    portfolio.equity = portfolio.current_balance + portfolio.exposure
                    portfolio.realized_pnl += pnl
                    if pnl > 0:
                        portfolio.wins += 1
                        
                    db.delete(pos)
                    continue
                    
                # Adaptive Holding Time
                # Simplified check for multi-tenant (just take profit)
                exit_reason = None
                exit_price = current_price
                
                if pos.side in ["BUY_YES", "BUY"]:
                    if current_price - pos.entry_price > 0.05:
                        exit_reason = "TAKE_PROFIT"
                elif pos.side in ["BUY_NO", "SELL"]:
                    if pos.entry_price - current_price > 0.05:
                        exit_reason = "TAKE_PROFIT"
                        
                if exit_reason:
                    pnl = 0.0
                    if pos.side in ["BUY_YES", "BUY"]:
                        pnl = (exit_price - pos.entry_price) * pos.quantity
                    elif pos.side in ["BUY_NO", "SELL"]:
                        pnl = (pos.entry_price - exit_price) * pos.quantity
                        
                    self._close_user_trade(db, pos.user_id, market_id, exit_price, pnl)
                    
                    position_cost = pos.entry_price * pos.quantity
                    portfolio.exposure = max(0.0, portfolio.exposure - position_cost)
                    portfolio.current_balance += (position_cost + pnl)
                    portfolio.equity = portfolio.current_balance + portfolio.exposure
                    portfolio.realized_pnl += pnl
                    if pnl > 0:
                        portfolio.wins += 1
                        
                    db.delete(pos)
                    continue

                # Update MTM
                # Note: keeping it simple for the SaaS demo
                
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating multi-tenant positions: {e}")
        finally:
            db.close()
            
    def _close_user_trade(self, db, user_id, market_id, exit_price, pnl):
        trade = db.query(UserTrade).filter(UserTrade.user_id == user_id, UserTrade.market_id == market_id, UserTrade.status == "OPEN").first()
        if trade:
            trade.status = "CLOSED"
            trade.exit_price = exit_price
            trade.pnl = pnl
            trade.exit_time = datetime.utcnow()

multi_tenant_engine = MultiTenantPaperEngine()
