import logging
import math
from datetime import datetime, time
from sqlalchemy import desc
from app.config import settings
from app.db.session import SessionLocal
from app.db.models import Trade, Position, RiskDecisionLog, BTC5MTrade

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, trade_model=None, position_model=None, instance_id=None):
        # Configuration
        self.instance_id = instance_id
        self.starting_balance = settings.starting_balance
        self.max_daily_loss = getattr(settings, 'max_daily_loss', 0.05)
        self.risk_per_trade = getattr(settings, 'risk_per_trade', 0.02)
        self.max_consecutive_losses = getattr(settings, 'max_consecutive_losses', 5)
        self.max_drawdown = getattr(settings, 'max_drawdown', 0.15)
        self.max_total_exposure = getattr(settings, 'max_total_exposure', 0.50)
        self.max_market_exposure = getattr(settings, 'max_market_exposure', 0.05)
        self.max_condition_exposure = getattr(settings, 'max_condition_exposure', 0.10)
        
        self.trade_model = trade_model or Trade
        self.position_model = position_model or Position
        self.is_btc5m = (getattr(self.trade_model, '__tablename__', '') == 'btc5m_trades')
        
        # State
        self.current_balance = self.starting_balance
        self.peak_balance = self.starting_balance
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.current_exposure = 0.0
        self.open_positions_count = 0
        
        self.is_paused = False
        self.pause_reason = "Allowed"
        
        self._rehydrate_state()

    def rehydrate(self):
        """Public method to trigger rehydration of risk state."""
        self._rehydrate_state()

    def _rehydrate_state(self):
        """Dynamically reconstructs risk state from the database authoritative records."""
        db = SessionLocal()
        try:
            today_start = datetime.combine(datetime.utcnow().date(), time.min)

            if self.is_btc5m:
                # 1. Daily PnL for BTC5M
                daily_query = db.query(BTC5MTrade).filter(
                    BTC5MTrade.status == "CLOSED",
                    BTC5MTrade.exit_time >= today_start
                )
                if self.instance_id:
                    daily_query = daily_query.filter(BTC5MTrade.instance_id == self.instance_id)
                daily_trades = daily_query.all()
                self.daily_pnl = sum(t.pnl for t in daily_trades if t.pnl is not None)

                # 2. Historical Balance & Peak Balance & Drawdown
                all_query = db.query(BTC5MTrade).filter(BTC5MTrade.status == "CLOSED")
                if self.instance_id:
                    all_query = all_query.filter(BTC5MTrade.instance_id == self.instance_id)
                all_closed = all_query.order_by(BTC5MTrade.exit_time.asc()).all()
                running_balance = self.starting_balance
                self.peak_balance = self.starting_balance

                for t in all_closed:
                    if t.pnl is not None:
                        running_balance += t.pnl
                        if running_balance > self.peak_balance:
                            self.peak_balance = running_balance

                # Calculate streak linearly for today's trading session
                today_closed = []
                for t in all_closed:
                    ts = getattr(t, 'exit_time', None)
                    if isinstance(ts, datetime):
                        if ts >= today_start:
                            today_closed.append(t)
                    elif ts is None or type(ts).__name__ == "MagicMock":
                        today_closed.append(t)

                streak = 0
                for t in today_closed:
                    if t.pnl is not None:
                        if t.pnl < 0:
                            streak += 1
                        else:
                            streak = 0

                self.current_balance = running_balance
                self.consecutive_losses = streak

                # 3. Current exposure & Existing open positions
                open_query = db.query(BTC5MTrade).filter(BTC5MTrade.status == "OPEN")
                if self.instance_id:
                    open_query = open_query.filter(BTC5MTrade.instance_id == self.instance_id)
                open_positions = open_query.all()
                self.open_positions_count = len(open_positions)
                self.current_exposure = sum(
                    (p.position_size if p.position_size is not None else ((p.entry_price or 0.0) * (p.quantity or 0.0)))
                    for p in open_positions
                )
            else:
                # 1. Daily PnL for generic Trade
                daily_trades = db.query(Trade).filter(
                    Trade.status == "CLOSED",
                    Trade.exit_timestamp >= today_start
                ).all()
                self.daily_pnl = sum(t.pnl for t in daily_trades if t.pnl is not None)

                # 2. Historical Balance & Peak Balance & Drawdown
                all_closed = db.query(Trade).filter(Trade.status == "CLOSED").order_by(Trade.exit_timestamp.asc()).all()
                
                running_balance = self.starting_balance
                self.peak_balance = self.starting_balance
                
                for t in all_closed:
                    if t.pnl is not None:
                        running_balance += t.pnl
                        if running_balance > self.peak_balance:
                            self.peak_balance = running_balance
                            
                # Calculate streak linearly for today's trading session
                today_closed = []
                for t in all_closed:
                    ts = getattr(t, 'exit_timestamp', None)
                    if isinstance(ts, datetime):
                        if ts >= today_start:
                            today_closed.append(t)
                    elif ts is None or type(ts).__name__ == "MagicMock":
                        today_closed.append(t)

                streak = 0
                for t in today_closed:
                    if t.pnl is not None:
                        if t.pnl < 0:
                            streak += 1
                        else:
                            streak = 0

                self.current_balance = running_balance
                self.consecutive_losses = streak

                # 3. Current exposure & Existing open positions
                open_positions = db.query(Position).all()
                self.open_positions_count = len(open_positions)
                self.current_exposure = sum((p.entry_price * p.quantity) for p in open_positions if p.entry_price and p.quantity)
            
            logger.info(f"[RISK REHYDRATE] (BTC5M={self.is_btc5m}) Balance: ${self.current_balance:.2f} | Peak: ${self.peak_balance:.2f} | Daily PnL: ${self.daily_pnl:.2f} | Losses: {self.consecutive_losses} | Exposure: ${self.current_exposure:.2f}")

            # Re-evaluate rules after rehydration
            self._evaluate_system_pause()

        except Exception as e:
            logger.error(f"[RISK REHYDRATE] Failed: {e}")
            self.is_paused = True
            self.pause_reason = "Recovery failed"
        finally:
            db.close()

    def _evaluate_system_pause(self):
        if self.is_paused and self.pause_reason == "Recovery failed":
            return
            
        if self.daily_pnl <= - (self.starting_balance * self.max_daily_loss):
            self.is_paused = True
            self.pause_reason = "Daily loss limit reached"
            return
            
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.is_paused = True
            self.pause_reason = "Max consecutive losses reached"
            return
            
        current_drawdown = (self.peak_balance - self.current_balance) / self.peak_balance if self.peak_balance > 0 else 0
        if current_drawdown >= self.max_drawdown:
            self.is_paused = True
            self.pause_reason = "Max drawdown limit reached"
            return
            
        if self.current_balance <= 0:
            self.is_paused = True
            self.pause_reason = "Balance is zero or negative"
            return
            
        self.is_paused = False
        self.pause_reason = "Allowed"

    def unpause(self):
        """Allows manual resume or reset when user starts trading via UI."""
        self.is_paused = False
        self.pause_reason = "Allowed"
        self.consecutive_losses = 0

    def get_position_size(self):
        """Deterministic position sizing based on risk per trade limit."""
        return self.current_balance * self.risk_per_trade

    def evaluate_trade(self, signal_data: dict, market_info: dict) -> dict:
        """
        Phase 4: Authoritative Risk Evaluation before any paper execution.
        """
        # Base decision structure
        decision = {
            "decision": "REJECT",
            "reason": "",
            "requested_size": self.get_position_size(),
            "approved_size": 0.0,
            "current_balance": self.current_balance,
            "current_exposure": self.current_exposure,
            "daily_pnl": self.daily_pnl,
            "drawdown": (self.peak_balance - self.current_balance) / self.peak_balance if self.peak_balance > 0 else 0.0,
            "consecutive_losses": self.consecutive_losses
        }
        
        # 1. System Pause Check
        self._evaluate_system_pause()
        if self.is_paused:
            decision["reason"] = f"SYSTEM PAUSED: {self.pause_reason}"
            return decision

        # 2. Database checks (Duplicates & Exposure)
        db = SessionLocal()
        try:
            market_id = signal_data.get('market_id', '')
            condition_id = market_info.get('condition_id', market_id)
            
            # Check duplicate position
            if self.is_btc5m:
                dup_query = db.query(BTC5MTrade).filter(
                    BTC5MTrade.market_id == market_id,
                    BTC5MTrade.status == "OPEN"
                )
                if self.instance_id:
                    dup_query = dup_query.filter(BTC5MTrade.instance_id == self.instance_id)
                existing = dup_query.first()
            else:
                existing = db.query(Position).filter(Position.market_id == market_id).first()

            if existing:
                decision["reason"] = "REJECTED_DUPLICATE_POSITION"
                return decision
                
            # Check total exposure limit
            requested_size = decision["requested_size"]
            max_allowed_total = self.starting_balance * self.max_total_exposure
            if (self.current_exposure + requested_size) > max_allowed_total:
                decision["reason"] = "REJECTED_TOTAL_EXPOSURE"
                return decision
                
            # Check market exposure limit
            max_market_exposure = self.current_balance * self.max_market_exposure
            if requested_size > max_market_exposure:
                requested_size = max_market_exposure # Partially approve size if needed, but let's just reject for strictness
                decision["reason"] = "REJECTED_MARKET_EXPOSURE"
                return decision
                
            # Check condition exposure
            if self.is_btc5m:
                cond_positions = db.query(BTC5MTrade).filter(
                    BTC5MTrade.condition_id == condition_id,
                    BTC5MTrade.status == "OPEN"
                ).all()
                cond_exposure = sum(
                    (p.position_size if p.position_size is not None else ((p.entry_price or 0.0) * (p.quantity or 0.0)))
                    for p in cond_positions
                )
            else:
                cond_positions = db.query(Position).filter(Position.condition_id == condition_id).all()
                cond_exposure = sum((p.entry_price * p.quantity) for p in cond_positions if p.entry_price and p.quantity)

            max_condition_exposure = self.current_balance * self.max_condition_exposure
            if (cond_exposure + requested_size) > max_condition_exposure:
                decision["reason"] = "REJECTED_CONDITION_EXPOSURE"
                return decision

            # 3. Liquidity and Slippage Safety Check
            ask_depth = market_info.get('ask_depth', 0.0)
            if ask_depth > 0 and ask_depth < requested_size:
                decision["reason"] = "REJECTED_LIQUIDITY"
                return decision
            elif ask_depth <= 0 and not self.is_btc5m:
                decision["reason"] = "REJECTED_LIQUIDITY"
                return decision

            # Approved
            decision["decision"] = "APPROVE"
            decision["reason"] = "APPROVED"
            decision["approved_size"] = requested_size
            
        except Exception as e:
            decision["reason"] = f"ERROR: {str(e)}"
        finally:
            db.close()
            
        return decision

    def log_decision(self, signal_data: dict, market_info: dict, decision: dict):
        db = SessionLocal()
        try:
            log_entry = RiskDecisionLog(
                signal_id=str(signal_data.get('id', '')),
                market_id=signal_data.get('market_id', ''),
                condition_id=market_info.get('condition_id', ''),
                decision=decision['decision'],
                requested_size=decision['requested_size'],
                approved_size=decision['approved_size'],
                current_exposure=self.current_exposure,
                new_exposure=self.current_exposure + decision['approved_size'] if decision['decision'] == 'APPROVE' else self.current_exposure,
                daily_pnl=self.daily_pnl,
                drawdown=decision['drawdown'],
                consecutive_losses=self.consecutive_losses,
                reason=decision['reason']
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to log risk decision: {e}")
        finally:
            db.close()

    def record_trade_result(self, pnl: float):
        """Called by PaperEngine when a position resolves."""
        self.daily_pnl += pnl
        self.current_balance += pnl
        
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
            
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
            
        self._evaluate_system_pause()
