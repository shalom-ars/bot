from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, UserPortfolio, UserTrade, AuditLog, Subscription
from app.api.security import get_current_admin

router = APIRouter()

@router.get("/dashboard")
def get_admin_dashboard(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    pro_users = db.query(Subscription).filter(Subscription.plan == "PRO").count()
    total_trades = db.query(UserTrade).count()
    
    return {
        "metrics": {
            "total_users": total_users,
            "active_users": active_users,
            "pro_users": pro_users,
            "paper_trades": total_trades
        }
    }

@router.get("/users")
def get_users(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    users = db.query(User).offset(skip).limit(limit).all()
    return users

@router.get("/audit_logs")
def get_audit_logs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    from sqlalchemy import desc
    logs = db.query(AuditLog).order_by(desc(AuditLog.timestamp)).offset(skip).limit(limit).all()
    return logs
