from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db
from app.engine.scanner import orchestrator
import time

router = APIRouter()

START_TIME = time.time()

@router.get("")
def health_check():
    """Simple L7 health check for load balancers."""
    return {"status": "ok"}

@router.get("/detailed")
def detailed_health_check(db: Session = Depends(get_db)):
    """Detailed health check for internal monitoring."""
    health_status = {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "database": "disconnected",
        "orchestrator": orchestrator.get_health()
    }
    
    # Check Database
    try:
        db.execute(text("SELECT 1"))
        health_status["database"] = "connected"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
        
    return health_status
