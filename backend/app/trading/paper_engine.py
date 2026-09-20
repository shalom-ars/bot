import logging
import uuid
from datetime import datetime
from app.db.session import SessionLocal
from app.db.models import Trade, Position
from app.trading.risk import RiskManager

logger = logging.getLogger(__name__)

class PaperEngine:
    def __init__(self, risk_manager: RiskManager):
        self.risk = risk_manager

    def execute_signal(self, signal_data: dict, market_info: dict):
        # 1. Authoritative Risk Manager Check
        decision = self.risk.evaluate_trade(signal_data, market_info)
        
        # Log decision
        self.risk.log_decision(signal_data, market_info, decision)
        
        if decision["decision"] != "APPROVE":
            return False, decision["reason"]

        # 2. Extract Phase 3 Execution Info
        market_id = signal_data['market_id']
        condition_id = market_info.get('condition_id', market_id)
        token_id = market_id
        signal = signal_data['signal_type']
        
        # We must use simulated entry_price instead of mid price
        entry_price = signal_data.get('entry_price', signal_data.get('market_prob', 0.5))
        slippage = signal_data.get('slippage_cost', 0.0)
        fees = signal_data.get('fees', 0.0)
        
        # Calculate actual execution price
        execution_price = entry_price + slippage + fees
        
        # Hard filter against penny tokens and extreme prices
        if execution_price < 0.20 or execution_price > 0.80:
            logger.info(f"Signal rejected: execution price ${execution_price:.3f} outside safe corridor ($0.20 - $0.80)")
            return False, "Rejected: Penny or extreme token price"

        size = decision["approved_size"]
        quantity = size / execution_price if execution_price > 0 else 0
        
        trade_id = str(uuid.uuid4())
        
        db = SessionLocal()
        try:
            # 3. Create trade record
            trade = Trade(
                trade_id=trade_id,
                market_id=market_id,
                condition_id=condition_id,
                token_id=token_id,
                strategy=signal_data.get('strategy', 'UNKNOWN'),
                side=signal,
                requested_size=decision['requested_size'],
                approved_size=decision['approved_size'],
                entry_price=execution_price,
                quantity=quantity,
                position_value=size,
                model_probability=signal_data.get('model_prob', 0.5),
                market_probability=signal_data.get('market_prob', 0.5),
                edge=signal_data.get('effective_edge', 0.0),
                confidence=signal_data.get('confidence', 0.0),
                fees=fees,
                slippage=slippage,
                status="OPEN",
                reason="Signal executed",
                timestamp=datetime.utcnow(),
                entry_timestamp=datetime.utcnow()
            )
            db.add(trade)
            
            # 4. Create position record
            pos = Position(
                market_id=market_id,
                condition_id=condition_id,
                token_id=token_id,
                strategy=signal_data.get('strategy', 'UNKNOWN'),
                side=signal,
                entry_price=execution_price,
                quantity=quantity,
                current_price=execution_price, # Initial MTM is execution price
                unrealized_pnl=0.0,
                timestamp=datetime.utcnow()
            )
            db.add(pos)
            
            db.commit()
            # P0-001 FIX: update in-memory exposure immediately so risk limits work
            # during the current session without waiting for rehydration on restart
            self.risk.current_exposure += size
            self.risk.open_positions_count += 1
            logger.info(f"PAPER TRADE EXECUTED: {signal} on {market_id} @ {execution_price} | Size: {size}")
            return True, "Executed"
        except Exception as e:
            db.rollback()
            logger.error(f"Paper engine error: {e}")
            return False, str(e)
        finally:
            db.close()

    def update_positions(self, market_id: str, current_price: float, is_resolved: bool = False, resolved_price: float = 0.0):
        db = SessionLocal()
        try:
            pos = db.query(Position).filter(Position.market_id == market_id).first()
            if not pos:
                return

            if is_resolved:
                # Close the position
                pnl = 0.0
                if pos.side == "BUY_YES" or pos.side == "BUY":
                    pnl = (resolved_price - pos.entry_price) * pos.quantity
                elif pos.side == "BUY_NO" or pos.side == "SELL":
                    pnl = ((1.0 - resolved_price) - pos.entry_price) * pos.quantity

                trade = db.query(Trade).filter(Trade.market_id == market_id, Trade.status == "OPEN").first()
                if trade:
                    trade.status = "CLOSED"
                    trade.exit_price = resolved_price
                    trade.pnl = pnl
                    trade.exit_timestamp = datetime.utcnow()
                    trade.resolution_reason = "RESOLVED"
                
                self.risk.record_trade_result(pnl)
                db.delete(pos)
                db.commit()
                
                # P0-001 FIX: decrement in-memory exposure immediately
                position_cost = pos.entry_price * pos.quantity if pos.entry_price and pos.quantity else 0.0
                self.risk.current_exposure = max(0.0, self.risk.current_exposure - position_cost)
                self.risk.open_positions_count = max(0, self.risk.open_positions_count - 1)
                
                logger.info(f"Position closed on {market_id}, PnL: {pnl}")
                return
                
            # P1: Adaptive Holding Time (Max 15 minutes), $1.00 TP, and strict Stop Loss
            hold_time_hours = (datetime.utcnow() - pos.timestamp).total_seconds() / 3600.0
            
            exit_reason = None
            exit_price = current_price
            
            # Calculate profit margin and dollar PnL
            if pos.side in ["BUY_YES", "BUY"]:
                profit_margin = current_price - pos.entry_price
            else:
                profit_margin = pos.entry_price - current_price
            dollar_pnl = profit_margin * (pos.quantity if pos.quantity else 0.0)

            # 1. Take Profit ($1.00 target or >= 5c price delta)
            if dollar_pnl >= 1.00 or profit_margin >= 0.05:
                exit_reason = "TAKE_PROFIT"
            # 2. Fast Stop Loss (cut loss if drawdown exceeds 10% or -$0.50)
            elif dollar_pnl <= -0.50 or profit_margin <= -(0.10 * pos.entry_price):
                exit_reason = "STOP_LOSS"
            # 3. Time Stop (Max 15 minutes instead of 2 hours)
            elif hold_time_hours >= 0.25:
                exit_reason = "TIME_STOP"
                        
            if exit_reason:
                pnl = 0.0
                if pos.side in ["BUY_YES", "BUY"]:
                    pnl = (exit_price - pos.entry_price) * pos.quantity
                elif pos.side in ["BUY_NO", "SELL"]:
                    pnl = (pos.entry_price - exit_price) * pos.quantity
                    
                trade = db.query(Trade).filter(Trade.market_id == market_id, Trade.status == "OPEN").first()
                if trade:
                    trade.status = "CLOSED"
                    trade.exit_price = exit_price
                    trade.pnl = pnl
                    trade.exit_timestamp = datetime.utcnow()
                    trade.resolution_reason = exit_reason
                    
                self.risk.record_trade_result(pnl)
                db.delete(pos)
                db.commit()
                
                position_cost = pos.entry_price * pos.quantity if pos.entry_price and pos.quantity else 0.0
                self.risk.current_exposure = max(0.0, self.risk.current_exposure - position_cost)
                self.risk.open_positions_count = max(0, self.risk.open_positions_count - 1)
                
                logger.info(f"[PAPER] Exited {market_id} early due to {exit_reason} (PnL: ${pnl:.2f})")
                return

            # Update unrealized pnl
                if pos.side == "BUY_YES" or pos.side == "BUY":
                    pos.unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
                elif pos.side == "BUY_NO" or pos.side == "SELL":
                    # P1-006 FIX: NO token has value (1 - yes_price).
                    # unrealized PnL = (current NO token value - entry price) * qty
                    no_token_price = 1.0 - current_price
                    pos.unrealized_pnl = (no_token_price - pos.entry_price) * pos.quantity
                pos.current_price = current_price
                db.commit()
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating position: {e}")
        finally:
            db.close()
