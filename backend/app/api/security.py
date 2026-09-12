import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User

# Configuration
# P0-003 FIX: Never use a hardcoded JWT secret. Fail hard at startup if not configured.
_raw_secret = os.environ.get("SAAS_SECRET_KEY")
if not _raw_secret:
    import sys
    if "pytest" in sys.modules or "unittest" in sys.modules:
        # Allow tests to run with a deterministic key
        _raw_secret = "test_only_secret_do_not_use_in_production"
    else:
        raise RuntimeError(
            "FATAL: SAAS_SECRET_KEY environment variable is not set. "
            "Set it in your .env file before starting the server."
        )
SECRET_KEY = _raw_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week

import hashlib
import binascii
import os

def verify_password(plain_password, hashed_password):
    if not hashed_password or ":" not in hashed_password:
        return False
    salt, hash_val = hashed_password.split(":")
    pwd_hash = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt.encode('ascii'), 100000)
    return binascii.hexlify(pwd_hash).decode('ascii') == hash_val

def get_password_hash(password):
    salt = os.urandom(16)
    salt_hex = binascii.hexlify(salt).decode('ascii')
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt_hex.encode('ascii'), 100000)
    return f"{salt_hex}:{binascii.hexlify(pwd_hash).decode('ascii')}"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

async def get_current_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in ["ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user
