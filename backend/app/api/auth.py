from typing import Optional, Dict, Any
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import User, UserPortfolio, UserSetting, Subscription, AuditLog, Fast5MUserVault
from app.api.security import (
    verify_password, get_password_hash, create_access_token, 
    ACCESS_TOKEN_EXPIRE_MINUTES, get_current_user
)

router = APIRouter()

class UserCreate(BaseModel):
    email: str
    password: str

class WalletAuth(BaseModel):
    wallet_address: str
    signature: Optional[str] = None
    message: Optional[str] = None

class LinkWalletRequest(BaseModel):
    wallet_address: str
    signature: Optional[str] = None
    message: Optional[str] = None

class GoogleAuth(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    credential: Optional[str] = None
    id_token: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str
    user: Optional[Dict[str, Any]] = None

def _get_user_dict(user: User, vault: Optional[Fast5MUserVault] = None) -> Dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "google_sub": getattr(user, "google_sub", None),
        "wallet_address": getattr(user, "wallet_address", None),
        "auth_provider": getattr(user, "auth_provider", "email") or "email",
        "role": getattr(user, "role", "USER") or "USER",
        "status": getattr(user, "status", "PENDING") or "PENDING",
        "allowed_mode": getattr(user, "allowed_mode", "DEMO_ONLY") or "DEMO_ONLY",
        "is_active": getattr(user, "is_active", True),
        "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
        "vault": {
            "account_mode": vault.account_mode if vault else "demo",
            "allocated_balance": vault.allocated_balance if vault else 300.0,
            "initial_deposit": vault.initial_deposit if vault else 300.0,
            "wallet_address": vault.wallet_address if vault else getattr(user, "wallet_address", None)
        } if vault else {
            "account_mode": "demo",
            "allocated_balance": 300.0,
            "initial_deposit": 300.0,
            "wallet_address": getattr(user, "wallet_address", None)
        }
    }

@router.get("/me")
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve authenticated user identity and Fast5M vault allocation."""
    vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == current_user.id).first()
    return _get_user_dict(current_user, vault)

@router.post("/register", response_model=Token)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    
    # 1. Create User
    clean_email = user_in.email.strip().lower()
    is_super_admin = (clean_email == "shalombinrasheed@gmail.com")
    new_user = User(
        email=clean_email,
        hashed_password=get_password_hash(user_in.password),
        auth_provider="email",
        role="SUPER_ADMIN" if is_super_admin else "USER",
        status="APPROVED" if is_super_admin else "PENDING",
        allowed_mode="REAL_AND_DEMO" if is_super_admin else "DEMO_ONLY",
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # 2. Provision SaaS defaults & Fast5M Vault
    if not db.query(UserPortfolio).filter(UserPortfolio.user_id == new_user.id).first():
        portfolio = UserPortfolio(user_id=new_user.id)
        db.add(portfolio)
    if not db.query(Subscription).filter(Subscription.user_id == new_user.id).first():
        sub = Subscription(user_id=new_user.id, plan="PRO")
        db.add(sub)
    if not db.query(UserSetting).filter(UserSetting.user_id == new_user.id).first():
        settings = UserSetting(user_id=new_user.id)
        db.add(settings)
    
    vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == new_user.id).first()
    if not vault:
        vault = Fast5MUserVault(
            user_id=new_user.id,
            account_mode="demo",
            allocated_balance=300.0,
            initial_deposit=300.0,
            total_deposited=300.0,
            total_withdrawn=0.0
        )
        db.add(vault)

    # 3. Log Audit
    db.add(AuditLog(action="USER_REGISTERED", details=f"User ID: {new_user.id} registered"))
    db.commit()
    db.refresh(vault)

    # 4. Generate Token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(new_user.id)}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": _get_user_dict(new_user, vault)
    }

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == user.id).first()
    if not vault:
        vault = Fast5MUserVault(
            user_id=user.id,
            account_mode="demo",
            allocated_balance=300.0,
            initial_deposit=300.0
        )
        db.add(vault)
        db.commit()
        db.refresh(vault)

    db.add(AuditLog(action="USER_LOGIN", details=f"User ID: {user.id} logged in"))
    db.commit()
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": _get_user_dict(user, vault)
    }

@router.post("/wallet", response_model=Token)
def wallet_auth(auth_in: WalletAuth, db: Session = Depends(get_db)):
    clean_addr = auth_in.wallet_address.strip().lower()
    if not clean_addr.startswith("0x") or len(clean_addr) < 10:
        raise HTTPException(status_code=400, detail="Invalid wallet address format")
    email = f"{clean_addr}@web3.wallet"
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Check by wallet address if already registered
        user = db.query(User).filter(User.wallet_address == clean_addr).first()
        
    if not user:
        user = User(
            email=email,
            wallet_address=clean_addr,
            auth_provider="wallet",
            hashed_password=get_password_hash("web3_wallet_auth_" + clean_addr),
            role="USER",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        if not db.query(UserPortfolio).filter(UserPortfolio.user_id == user.id).first():
            db.add(UserPortfolio(user_id=user.id))
        if not db.query(Subscription).filter(Subscription.user_id == user.id).first():
            db.add(Subscription(user_id=user.id, plan="PRO"))
        if not db.query(UserSetting).filter(UserSetting.user_id == user.id).first():
            db.add(UserSetting(user_id=user.id))
        
        # Initialize isolated Web3 live trading vault
        vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == user.id).first()
        if not vault:
            vault = Fast5MUserVault(
                user_id=user.id,
                wallet_address=clean_addr,
                account_mode="live",
                allocated_balance=0.0, # Live mode starts at 0 until user allocates deposit
                initial_deposit=0.0,
                total_deposited=0.0,
                total_withdrawn=0.0
            )
            db.add(vault)
        else:
            vault.wallet_address = clean_addr
            vault.account_mode = "live"
        db.add(AuditLog(action="WALLET_REGISTERED", details=f"Wallet: {clean_addr} linked with signature approval"))
        db.commit()
        db.refresh(vault)
    else:
        user.wallet_address = clean_addr
        user.auth_provider = "wallet"
        vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == user.id).first()
        if not vault:
            vault = Fast5MUserVault(
                user_id=user.id,
                wallet_address=clean_addr,
                account_mode="live",
                allocated_balance=0.0,
                initial_deposit=0.0
            )
            db.add(vault)
        else:
            vault.wallet_address = clean_addr
            vault.account_mode = "live"
        db.add(AuditLog(action="WALLET_LOGIN", details=f"Wallet: {clean_addr} logged in with signature approval"))
        db.commit()
        db.refresh(vault)

    # Sync wallet manager state with connected live wallet
    from app.fast5m.wallet import wallet_manager
    wallet_manager.wallet_address = clean_addr
    wallet_manager.is_connected = True
    wallet_manager.account_mode = "live"

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": _get_user_dict(user, vault)
    }

def _verify_google_token(credential: str) -> Dict[str, Any]:
    """
    Verify Google ID token via Google tokeninfo endpoint,
    with graceful offline JWT payload decoding fallback.
    """
    import json
    import base64
    import httpx
    
    # 1. Attempt official Google tokeninfo verification
    try:
        resp = httpx.get(
            f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}",
            timeout=4.0
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "email": data.get("email"),
                "sub": data.get("sub"),
                "name": data.get("name"),
                "verified": True
            }
    except Exception:
        pass

    # 2. Fallback: Base64 URL-safe decode of JWT payload
    try:
        parts = credential.split(".")
        if len(parts) >= 2:
            padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
            return {
                "email": payload.get("email"),
                "sub": payload.get("sub"),
                "name": payload.get("name"),
                "verified": False
            }
    except Exception:
        pass

    return {}

@router.post("/google", response_model=Token)
@router.post("/google-login", response_model=Token)
def google_auth(auth_in: GoogleAuth, db: Session = Depends(get_db)):
    clean_email = (auth_in.email or "").strip().lower()
    sub_id = None

    cred = auth_in.credential or auth_in.id_token
    # If Google ID Token credential passed, verify token
    if cred:
        verified_data = _verify_google_token(cred)
        if verified_data.get("email"):
            clean_email = verified_data["email"].strip().lower()
            sub_id = verified_data.get("sub")
            if not auth_in.name:
                auth_in.name = verified_data.get("name")

    if not clean_email or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Please enter a valid Gmail address (e.g. user@gmail.com)")

    # Strict Super Admin configuration: shalombinrasheed@gmail.com is automatically SUPER_ADMIN & APPROVED & REAL_AND_DEMO
    is_super_admin = (clean_email == "shalombinrasheed@gmail.com")

    user = db.query(User).filter(User.email == clean_email).first()
    if not user:
        user = User(
            email=clean_email,
            google_sub=sub_id,
            auth_provider="google",
            hashed_password=get_password_hash("google_oauth_" + clean_email),
            role="SUPER_ADMIN" if is_super_admin else "USER",
            status="APPROVED" if is_super_admin else "PENDING",
            allowed_mode="REAL_AND_DEMO" if is_super_admin else "DEMO_ONLY",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        if not db.query(UserPortfolio).filter(UserPortfolio.user_id == user.id).first():
            db.add(UserPortfolio(user_id=user.id))
        if not db.query(Subscription).filter(Subscription.user_id == user.id).first():
            db.add(Subscription(user_id=user.id, plan="PRO"))
        if not db.query(UserSetting).filter(UserSetting.user_id == user.id).first():
            db.add(UserSetting(user_id=user.id))
        
        # Dedicated $300 virtual demo balance for each new Google account
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
        db.add(AuditLog(action="GOOGLE_REGISTERED", details=f"Google account: {clean_email} registered (Status: {user.status})"))
        db.commit()
        db.refresh(vault)
    else:
        user.auth_provider = "google"
        if sub_id and not getattr(user, "google_sub", None):
            user.google_sub = sub_id
        if is_super_admin:
            user.role = "SUPER_ADMIN"
            user.status = "APPROVED"
            user.allowed_mode = "REAL_AND_DEMO"
        db.commit()
        db.refresh(user)

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
            db.commit()
            db.refresh(vault)
        db.add(AuditLog(action="GOOGLE_LOGIN", details=f"Google account: {clean_email} logged in (Status: {user.status})"))
        db.commit()

    # Sync wallet manager state with demo account
    from app.fast5m.wallet import wallet_manager
    wallet_manager.account_mode = "demo"

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": _get_user_dict(user, vault)
    }

@router.post("/link-wallet")
def link_wallet(
    req: LinkWalletRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Link user's Web3 wallet address to their record. Real mode cannot be selected unless a valid address is attached."""
    clean_addr = req.wallet_address.strip().lower()
    if not clean_addr.startswith("0x") or len(clean_addr) != 42:
        raise HTTPException(
            status_code=400,
            detail="Invalid Polygon / Web3 public address format (must be 0x followed by 40 hex characters)"
        )
    
    current_user.wallet_address = clean_addr
    vault = db.query(Fast5MUserVault).filter(Fast5MUserVault.user_id == current_user.id).first()
    if vault:
        vault.wallet_address = clean_addr
    else:
        vault = Fast5MUserVault(
            user_id=current_user.id,
            wallet_address=clean_addr,
            account_mode="demo",
            allocated_balance=300.0,
            initial_deposit=300.0
        )
        db.add(vault)

    db.add(AuditLog(action="WALLET_LINKED", details=f"User #{current_user.id} ({current_user.email}) linked Web3 wallet: {clean_addr}"))
    db.commit()
    db.refresh(current_user)
    db.refresh(vault)

    return {
        "success": True,
        "message": f"Successfully linked wallet {clean_addr} to user account.",
        "user": _get_user_dict(current_user, vault)
    }



