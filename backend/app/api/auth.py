from typing import Optional
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import User, UserPortfolio, UserSetting, Subscription, AuditLog
from app.api.security import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter()

class UserCreate(BaseModel):
    email: str
    password: str

class WalletAuth(BaseModel):
    wallet_address: str

class GoogleAuth(BaseModel):
    email: str
    name: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

@router.post("/register", response_model=Token)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    
    # 1. Create User
    new_user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        role="USER",
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # 2. Provision SaaS defaults
    portfolio = UserPortfolio(user_id=new_user.id)
    subscription = Subscription(user_id=new_user.id, plan="FREE")
    settings = UserSetting(user_id=new_user.id)
    
    db.add(portfolio)
    db.add(subscription)
    db.add(settings)
    
    # 3. Audit
    db.add(AuditLog(action="USER_REGISTERED", details=f"User ID: {new_user.id} registered"))
    db.commit()

    # 4. Generate Token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(new_user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    db.add(AuditLog(action="USER_LOGIN", details=f"User ID: {user.id} logged in"))
    db.commit()
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/wallet", response_model=Token)
def wallet_auth(auth_in: WalletAuth, db: Session = Depends(get_db)):
    clean_addr = auth_in.wallet_address.strip().lower()
    if not clean_addr.startswith("0x") or len(clean_addr) < 10:
        raise HTTPException(status_code=400, detail="Invalid wallet address format")
    email = f"{clean_addr}@web3.wallet"
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            hashed_password=get_password_hash("web3_wallet_auth_" + clean_addr),
            role="USER",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(UserPortfolio(user_id=user.id))
        db.add(Subscription(user_id=user.id, plan="PRO"))
        db.add(UserSetting(user_id=user.id))
        db.add(AuditLog(action="WALLET_REGISTERED", details=f"Wallet: {clean_addr} linked for Real Money trading"))
        db.commit()
    else:
        db.add(AuditLog(action="WALLET_LOGIN", details=f"Wallet: {clean_addr} logged in"))
        db.commit()

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/google", response_model=Token)
def google_auth(auth_in: GoogleAuth, db: Session = Depends(get_db)):
    clean_email = auth_in.email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise HTTPException(status_code=400, detail="Invalid Google email address")
    user = db.query(User).filter(User.email == clean_email).first()
    if not user:
        user = User(
            email=clean_email,
            hashed_password=get_password_hash("google_oauth_" + clean_email),
            role="USER",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(UserPortfolio(user_id=user.id))
        db.add(Subscription(user_id=user.id, plan="PRO"))
        db.add(UserSetting(user_id=user.id))
        db.add(AuditLog(action="GOOGLE_REGISTERED", details=f"Google Email: {clean_email} registered"))
        db.commit()
    else:
        db.add(AuditLog(action="GOOGLE_LOGIN", details=f"Google Email: {clean_email} logged in"))
        db.commit()

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

