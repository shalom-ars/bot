import logging
from app.db.session import SessionLocal
from app.db.models import PaperTestSession, Market, CircuitBreakerEvent
from app.config import settings

logger = logging.getLogger(__name__)

class LiveEligibilityGate:
    """
    Validates that the system is fully prepared and legally permitted to submit real orders.
    Default status must always be NOT_ELIGIBLE unless strictly verified.
    """
    
    @staticmethod
    def check_eligibility() -> dict:
        status = {
            "eligible": False,
            "reasons": []
        }
        
        # 1. Config Check
        if not settings.live_trading_enabled:
            status["reasons"].append("CONFIG: live_trading_enabled is False")
        if settings.execution_mode != "live":
            status["reasons"].append(f"CONFIG: execution_mode is '{settings.execution_mode}', must be 'live'")
        if settings.live_trading_kill_switch:
            status["reasons"].append("SAFETY: KILL SWITCH IS ENABLED")
            
        # 2. Database & Phase 6 Paper Test Checks
        db = SessionLocal()
        try:
            # Phase 6 Paper Session Check
            paper_session = db.query(PaperTestSession).filter(PaperTestSession.status == "RUNNING").first()
            if not paper_session:
                status["reasons"].append("PHASE 6: No active paper test session found")
            else:
                if paper_session.closed_trades < 50:
                    status["reasons"].append(f"PHASE 6: Insufficient paper trades ({paper_session.closed_trades}/50 required)")
                if paper_session.drawdown > 0.15:
                    status["reasons"].append(f"PHASE 6: Excessive paper drawdown ({paper_session.drawdown*100:.1f}%)")
            
            # Research Readiness Check
            resolved_count = db.query(Market).filter(Market.resolved == True).count()
            if resolved_count < settings.min_resolved_markets:
                status["reasons"].append(f"RESEARCH: Insufficient resolved markets ({resolved_count}/{settings.min_resolved_markets})")
                
            # Circuit Breaker Check
            active_cb = db.query(CircuitBreakerEvent).filter(CircuitBreakerEvent.resolved == False).count()
            if active_cb > 0:
                status["reasons"].append(f"SYSTEM: {active_cb} active circuit breaker events are unresolved")
                
        except Exception as e:
            status["reasons"].append(f"DATABASE: Could not verify eligibility: {str(e)}")
        finally:
            db.close()
            
        # Final Decision
        if len(status["reasons"]) == 0:
            status["eligible"] = True
            
        return status
