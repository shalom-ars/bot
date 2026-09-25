from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import User, UserPortfolio, UserTrade, AuditLog, Subscription, Fast5MUserVault, Fast5MTrade
from app.api.security import get_current_super_admin

router = APIRouter()


class UserStatusUpdate(BaseModel):
    status: str # "APPROVED", "SUSPENDED", "PENDING"


class UserModeUpdate(BaseModel):
    allowed_mode: str # "DEMO_ONLY", "REAL_AND_DEMO", "NONE"


@router.get("/dashboard")
def get_admin_dashboard(
    db: Session = Depends(get_db), 
    admin: User = Depends(get_current_super_admin)
):
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    approved_users = db.query(User).filter(User.status == "APPROVED").count()
    pending_users = db.query(User).filter(User.status == "PENDING").count()
    suspended_users = db.query(User).filter(User.status == "SUSPENDED").count()
    real_mode_users = db.query(User).filter(User.allowed_mode == "REAL_AND_DEMO").count()
    total_trades = db.query(Fast5MTrade).count()
    
    return {
        "metrics": {
            "total_users": total_users,
            "active_users": active_users,
            "approved_users": approved_users,
            "pending_users": pending_users,
            "suspended_users": suspended_users,
            "real_mode_users": real_mode_users,
            "fast5m_trades": total_trades
        }
    }


@router.get("/users")
def get_users(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db), 
    admin: User = Depends(get_current_super_admin)
):
    """List all registered platform users with access status, permissions, wallet, and vault balance."""
    users = db.query(User).order_by(User.id.desc()).offset(skip).limit(limit).all()
    
    result = []
    for u in users:
        vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == u.id).first()
        total_trades = db.query(Fast5MTrade).filter(Fast5MTrade.user_id == u.id).count()
        open_trades = db.query(Fast5MTrade).filter(Fast5MTrade.user_id == u.id, Fast5MTrade.status == "OPEN").count()

        result.append({
            "id": u.id,
            "email": u.email,
            "google_sub": getattr(u, "google_sub", None),
            "role": getattr(u, "role", "USER") or "USER",
            "status": getattr(u, "status", "PENDING") or "PENDING",
            "allowed_mode": getattr(u, "allowed_mode", "DEMO_ONLY") or "DEMO_ONLY",
            "wallet_address": getattr(u, "wallet_address", None),
            "auth_provider": getattr(u, "auth_provider", "email") or "email",
            "is_active": getattr(u, "is_active", True),
            "allocated_balance": vault.allocated_balance if vault else 300.0,
            "total_trades": total_trades,
            "open_trades": open_trades,
            "created_at": u.created_at.isoformat() if getattr(u, "created_at", None) else None
        })
    return result


@router.post("/users/{user_id}/status")
def update_user_status(
    user_id: int,
    req: UserStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_super_admin)
):
    """Update user authorization status (APPROVED, SUSPENDED, PENDING)."""
    target_status = req.status.strip().upper()
    if target_status not in ["APPROVED", "SUSPENDED", "PENDING"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{req.status}'. Must be one of: APPROVED, SUSPENDED, PENDING."
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User #{user_id} not found.")

    # Protect primary super admin account from demotion/suspension
    if user.email == "arsandhuthree@gmail.com" and target_status != "APPROVED":
        raise HTTPException(status_code=400, detail="Cannot alter status of primary Super Administrator account.")

    old_status = getattr(user, "status", "PENDING")
    user.status = target_status

    # Ensure vault is provisioned if approving for the first time
    vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == user.id).first()
    if not vault:
        vault = Fast5MUserVault(
            user_id=user.id,
            account_mode="demo",
            allocated_balance=300.0,
            initial_deposit=300.0,
            total_deposited=300.0,
            total_withdrawn=0.0
        )
        db.add(vault)

    db.add(AuditLog(
        action="USER_STATUS_UPDATED",
        details=f"Admin #{admin.id} changed User #{user.id} ({user.email}) status from {old_status} to {target_status}"
    ))
    db.commit()
    db.refresh(user)

    return {
        "success": True,
        "message": f"Successfully updated User #{user.id} status to {target_status}.",
        "user_id": user.id,
        "email": user.email,
        "status": user.status
    }


@router.post("/users/{user_id}/mode")
def update_user_mode(
    user_id: int,
    req: UserModeUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_super_admin)
):
    """Update user permitted trading execution mode (DEMO_ONLY, REAL_AND_DEMO, NONE)."""
    target_mode = req.allowed_mode.strip().upper()
    if target_mode not in ["DEMO_ONLY", "REAL_AND_DEMO", "NONE"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{req.allowed_mode}'. Must be one of: DEMO_ONLY, REAL_AND_DEMO, NONE."
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User #{user_id} not found.")

    # Protect primary super admin account
    if user.email == "arsandhuthree@gmail.com" and target_mode != "REAL_AND_DEMO":
        raise HTTPException(status_code=400, detail="Cannot restrict trading mode of primary Super Administrator account.")

    old_mode = getattr(user, "allowed_mode", "DEMO_ONLY")
    user.allowed_mode = target_mode

    db.add(AuditLog(
        action="USER_MODE_UPDATED",
        details=f"Admin #{admin.id} changed User #{user.id} ({user.email}) mode from {old_mode} to {target_mode}"
    ))
    db.commit()
    db.refresh(user)

    return {
        "success": True,
        "message": f"Successfully updated User #{user.id} allowed mode to {target_mode}.",
        "user_id": user.id,
        "email": user.email,
        "allowed_mode": user.allowed_mode
    }


@router.get("/audit_logs")
def get_audit_logs(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db), 
    admin: User = Depends(get_current_super_admin)
):
    logs = db.query(AuditLog).order_by(desc(AuditLog.timestamp)).offset(skip).limit(limit).all()
    return logs
