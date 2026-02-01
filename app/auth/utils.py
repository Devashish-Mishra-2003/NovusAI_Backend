# app/auth/utils.py

from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from typing import Optional

from app.config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

ACCESS_TOKEN_EXPIRE_DAYS = 7


def get_password_hash(password: str) -> str:
    if not password or not password.strip():
        raise ValueError("Password cannot be empty")
    return pwd_context.hash(password.strip())


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password:
        return False
    return pwd_context.verify(plain_password.strip(), hashed_password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    )
    to_encode.update({"exp": expire})
    # Ensure "sub" is always a string
    if "sub" in to_encode and not isinstance(to_encode["sub"], str):
        to_encode["sub"] = str(to_encode["sub"])

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )