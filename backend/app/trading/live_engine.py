import logging
import uuid
from typing import Dict, Any
from app.db.session import SessionLocal
from app.db.models import LiveOrder, CircuitBreakerEvent, AuditLog
from app.trading.eligibility import LiveEligibilityGate
from app.trading.risk import RiskManager
from app.config import settings

logger = logging.getLogger(__name__)

class LiveExecutionEngine:
    def __init__(self, risk_manager: RiskManager):
        self.risk = risk_manager
    
    def log_audit(self, action: str, details: str):
        db = SessionLocal()
        try:
            db.add(AuditLog(action=action, details=details))
            db.commit()
        except Exception as e:
            logger.error(f"Audit log failed: {e}")
        finally:
            db.close()

    def trip_circuit_breaker(self, event_type: str, reason: str):
        logger.critical(f"CIRCUIT BREAKER TRIPPED: {event_type} - {reason}")
        db = SessionLocal()
        try:
            db.add(CircuitBreakerEvent(event_type=event_type, reason=reason))
            db.commit()
        except Exception as e:
            logger.error(f"Failed to record circuit breaker: {e}")
        finally:
            db.close()
            
    def execute_signal(self, signal: Dict[str, Any], market_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        The absolute entry point for submitting a real order.
        Guarded heavily against accidental execution.
        """
        # 1. HARD CONFIGURATION GUARD (Never bypass)
        if settings.execution_mode == "paper":
            logger.warning("LiveExecutionEngine called while in PAPER mode. Blocking execution.")
            return {"status": "BLOCKED", "reason": "EXECUTION_MODE_IS_PAPER"}
            
        if settings.live_trading_kill_switch:
            self.log_audit("BLOCKED_BY_KILL_SWITCH", f"Signal {signal.get('id')} blocked")
            return {"status": "BLOCKED", "reason": "KILL_SWITCH_ACTIVE"}
            
        # 2. ELIGIBILITY GATE
        eligibility = LiveEligibilityGate.check_eligibility()
        if not eligibility["eligible"]:
            self.log_audit("BLOCKED_BY_ELIGIBILITY_GATE", str(eligibility["reasons"]))
            return {"status": "BLOCKED", "reason": "ELIGIBILITY_GATE_FAILED", "details": eligibility["reasons"]}
            
        # 3. RISK MANAGER GATE
        # Risk Manager maintains identical exposure/drawdown sizing for both paper and live.
        risk_decision = self.risk.evaluate_trade(signal, market_info)
        if risk_decision["decision"] == "REJECT":
            self.log_audit("BLOCKED_BY_RISK_MANAGER", risk_decision["reason"])
            return {"status": "BLOCKED", "reason": risk_decision["reason"]}
            
        # 4. ORDER VALIDATION & IDEMPOTENCY
        market_id = signal.get("market_id")
        token_id = signal.get("token_id")
        side = "BUY" if signal.get("direction") == 1 else "SELL" # Simplified for architecture demonstration
        price = market_info.get("ask_price") + market_info.get("slippage", 0) # ALWAYS simulate worst case
        quantity = risk_decision["size"]
        
        if not market_id or not token_id or price <= 0 or quantity <= 0:
            return {"status": "BLOCKED", "reason": "MALFORMED_ORDER_PARAMETERS"}
            
        client_id = f"lo_{uuid.uuid4().hex}"
        
        # 5. STATE MACHINE INITIATION
        db = SessionLocal()
        try:
            # Idempotency check logic goes here if client_id was derived from signal hash
            
            live_order = LiveOrder(
                client_id=client_id,
                market_id=market_id,
                condition_id=market_info.get("condition_id", ""),
                token_id=token_id,
                side=side,
                price=price,
                quantity=quantity,
                state="CREATED"
            )
            db.add(live_order)
            db.commit()
            
            self.log_audit("ORDER_CREATED", f"Client ID: {client_id}, Market: {market_id}, Size: {quantity}")
            
            # 6. SIMULATED API SUBMISSION (Since REAL execution is blocked)
            live_order.state = "SUBMITTED"
            db.commit()
            
            # NOTE: Under Phase 7 rules, we do NOT submit a real order.
            # This architecture stops exactly here for now.
            live_order.state = "FAILED"
            live_order.error_reason = "LIVE_ORDER_SUBMISSION_DISABLED_PHASE7"
            db.commit()
            
            self.log_audit("ORDER_FAILED", "Phase 7 explicitly disables real API submission.")
            return {"status": "FAILED", "reason": "LIVE_ORDER_SUBMISSION_DISABLED_PHASE7"}
            
        except Exception as e:
            logger.error(f"Live engine error: {e}")
            self.trip_circuit_breaker("DATABASE_ERROR", str(e))
            return {"status": "ERROR", "reason": str(e)}
        finally:
            db.close()
