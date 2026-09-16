from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, UserPortfolio
from app.api.security import get_current_user
from app.engine.scanner import orchestrator

router = APIRouter()

class ControlAction(BaseModel):
    action: str
    reason: str = ""

@router.get("/status")
def get_system_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    portfolio = db.query(UserPortfolio).filter(UserPortfolio.user_id == current_user.id).first()
    status = portfolio.paper_status if portfolio else "STOPPED"
    
    # Also ensure the global orchestrator is at least running so the backend scanner works
    global_status = orchestrator.paper_controller.get_status()
    if global_status not in ["RUNNING"]:
        orchestrator.paper_controller.resume_session()

    return {"paper_trading_status": status}

@router.post("/control")
def control_system(action_req: ControlAction, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    action = action_req.action.upper()
    portfolio = db.query(UserPortfolio).filter(UserPortfolio.user_id == current_user.id).first()
    
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    if action == "START":
        portfolio.paper_status = "RUNNING"
    elif action == "PAUSE":
        portfolio.paper_status = "PAUSED"
    elif action == "RESUME":
        portfolio.paper_status = "RUNNING"
    elif action == "STOP":
        portfolio.paper_status = "STOPPED"
    elif action == "EMERGENCY_STOP":
        portfolio.paper_status = "EMERGENCY_STOP"
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
        
    db.commit()
    
    # Ensure global scanner is running if ANY user is running
    global_status = orchestrator.paper_controller.get_status()
    if global_status not in ["RUNNING", "PAUSED"] and action in ["START", "RESUME"]:
        orchestrator.paper_controller._ensure_active_session()
        orchestrator.paper_controller.resume_session()
        
    return {"status": "success", "new_state": portfolio.paper_status}
