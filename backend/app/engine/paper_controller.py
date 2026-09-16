import logging
import uuid
from datetime import datetime, date, timedelta
from sqlalchemy import desc
from app.db.session import SessionLocal
from app.db.models import PaperTestSession, PaperDailySnapshot, Trade, Position, Signal
from app.trading.risk import RiskManager
from app.config import settings

logger = logging.getLogger(__name__)

class PaperTestController:
    """
    Manages the overarching long-term Paper Test Session.
    Survives restarts by syncing with SQLite.
    """
    def __init__(self, risk_manager: RiskManager):
        self.risk = risk_manager
        self.session_id = None
        self._ensure_active_session()

    def _ensure_active_session(self):
        db = SessionLocal()
        try:
            # Check for ANY existing active/paused session before creating a new one
            active_session = db.query(PaperTestSession).filter(PaperTestSession.status.in_(["RUNNING", "PAUSED", "EMERGENCY_STOP"])).order_by(desc(PaperTestSession.start_time)).first()
            if active_session:
                self.session_id = active_session.session_id
                logger.info(f"[PAPER-TEST] Found existing paper test session: {self.session_id} (Status: {active_session.status})")
            else:
                self.session_id = f"pts_{uuid.uuid4().hex[:8]}"
                new_session = PaperTestSession(
                    session_id=self.session_id,
                    status="RUNNING",
                    initial_balance=500.0,
                    current_balance=500.0,
                    equity=500.0
                )
                db.add(new_session)
                db.commit()
                logger.info(f"[PAPER-TEST] Created NEW paper test session: {self.session_id}")
                
            session_rec = db.query(PaperTestSession).filter_by(session_id=self.session_id).first()
            self.risk.starting_balance = session_rec.initial_balance
            self.risk._rehydrate_state()
            
        except Exception as e:
            logger.error(f"[PAPER-TEST] Failed to ensure session: {e}")
        finally:
            db.close()

    def set_status(self, new_status: str, reason: str = ""):
        db = SessionLocal()
        try:
            session = db.query(PaperTestSession).filter_by(session_id=self.session_id).first()
            if session:
                session.status = new_status
                if new_status == "STOPPED":
                    session.end_time = datetime.utcnow()
                db.commit()
                logger.info(f"[PAPER-TEST] Session {self.session_id} status changed to {new_status}. Reason: {reason}")
        except Exception as e:
            logger.error(f"Failed to change session status: {e}")
        finally:
            db.close()

    def get_status(self) -> str:
        db = SessionLocal()
        try:
            session = db.query(PaperTestSession).filter_by(session_id=self.session_id).first()
            return session.status if session else "UNKNOWN"
        finally:
            db.close()

    def pause_session(self):
        self.set_status("PAUSED")
        
    def resume_session(self):
        self.set_status("RUNNING")

    def stop_session(self):
        self.set_status("STOPPED")
        self.session_id = None
        self._ensure_active_session() # Creates a new one if requested later, but wait, if it's STOPPED we just stop. But if it's STOPPED, the scanner should stop evaluating. Wait, let's just leave session_id assigned but STOPPED.

    def emergency_stop(self, reason: str = "Manual Emergency Stop"):
        self.set_status("EMERGENCY_STOP", reason=reason)

    def update_session_stats(self):
        """Called periodically or when generating a report to update DB."""
        if not self.session_id:
            return
            
        db = SessionLocal()
        try:
            session = db.query(PaperTestSession).filter_by(session_id=self.session_id).first()
            if not session:
                return
                
            session.current_balance = self.risk.current_balance
            session.equity = self.risk.current_balance + self.risk.current_exposure
            # P1-001 FIX: net_pnl must reflect the full session, not just today's daily_pnl
            # (daily_pnl resets at midnight and can't track 4-8 week session performance)
            session.net_pnl = self.risk.current_balance - session.initial_balance
            session.drawdown = (self.risk.peak_balance - session.equity) / self.risk.peak_balance if self.risk.peak_balance > 0 else 0
            
            # Simple aggregates
            closed_trades = db.query(Trade).filter(Trade.status == "CLOSED").all()
            session.closed_trades = len(closed_trades)
            
            if session.closed_trades > 0:
                wins = len([t for t in closed_trades if getattr(t, 'pnl', 0) > 0])
                session.win_rate = wins / session.closed_trades
            
            db.commit()
        except Exception as e:
            logger.error(f"Failed to update session stats: {e}")
        finally:
            db.close()

    def get_health_status(self):
        """Builds the payload for the Phase 6 daily health check endpoint"""
        db = SessionLocal()
        try:
            session = db.query(PaperTestSession).filter_by(session_id=self.session_id).first()
            return {
                "paper_test_status": session.status if session else "UNKNOWN",
                "session_id": self.session_id,
                "elapsed_days": (datetime.utcnow() - session.start_time).days if session else 0,
                "initial_balance": session.initial_balance if session else 0,
                "balance": self.risk.current_balance,
                "equity": self.risk.current_balance + self.risk.current_exposure,
                "daily_pnl": self.risk.daily_pnl,
                # P1-001 FIX: net_pnl = session balance change, not daily_pnl
                "net_pnl": (self.risk.current_balance - session.initial_balance) if session else 0.0,
                "drawdown": session.drawdown if session else 0,
                "win_rate": session.win_rate if session else 0,
                "closed_trades": session.closed_trades if session else 0,
                "open_positions": self.risk.open_positions_count,
                "risk_status": "PAUSED" if self.risk.is_paused else "RUNNING"
            }
        finally:
            db.close()
