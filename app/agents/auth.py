# app/agents/auth.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session

from app.models.auth import Company, User, UserRole, UserStatus
from app.auth.utils import verify_password, get_password_hash, create_access_token
from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthUser
from app.db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


# ======================================================
# REQUEST / RESPONSE MODELS
# ======================================================

class CompanySignup(BaseModel):
    company_name: str
    email: str
    password: str
    admin_name: str = "Admin"


class UserCreate(BaseModel):
    company_name: str
    email: str
    password: str
    name: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PendingUser(BaseModel):
    id: int
    email: str
    name: str


# ======================================================
# COMPANY SIGNUP — INSTANT ADMIN
# ======================================================

@router.post("/company/signup", response_model=Token)
def company_signup(data: CompanySignup, db: Session = Depends(get_db)):
    if db.query(Company).filter(Company.name == data.company_name).first():
        raise HTTPException(400, "Company already exists")

    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Email already registered")

    company = Company(name=data.company_name)
    db.add(company)
    db.commit()
    db.refresh(company)

    admin = User(
        company_id=company.id,
        email=data.email,
        password_hash=get_password_hash(data.password),
        name=data.admin_name,
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    # ONLY store user ID in token
    access_token = create_access_token({"sub": admin.id})

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


# ======================================================
# EMPLOYEE SIGNUP — PENDING
# ======================================================

@router.post("/employee/signup")
def employee_signup(data: UserCreate, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.name == data.company_name).first()
    if not company:
        raise HTTPException(400, "Company not found")

    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Email already registered")

    user = User(
        company_id=company.id,
        email=data.email,
        password_hash=get_password_hash(data.password),
        name=data.name,
        role=UserRole.EMPLOYEE,
        status=UserStatus.PENDING,
    )
    db.add(user)
    db.commit()

    return {"message": "Signup successful. Awaiting admin approval."}


# ======================================================
# LOGIN
# ======================================================

@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Account not active")

    # ONLY store user ID in token
    access_token = create_access_token({"sub": user.id})

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


# ======================================================
# ADMIN — LIST PENDING USERS
# ======================================================

@router.get("/admin/pending", response_model=List[PendingUser])
def list_pending(
    current_user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    pending = (
        db.query(User)
        .filter(
            User.company_id == current_user.company_id,
            User.status == UserStatus.PENDING,
        )
        .all()
    )

    return [{"id": u.id, "email": u.email, "name": u.name} for u in pending]


# ======================================================
# ADMIN — APPROVE USER
# ======================================================

@router.post("/admin/approve/{user_id}")
def approve_user(
    user_id: int,
    current_user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.company_id == current_user.company_id,
        )
        .first()
    )

    if not user:
        raise HTTPException(404, "User not found")

    user.status = UserStatus.ACTIVE
    db.commit()

    return {"message": "User approved"}


# ======================================================
# COMPANY LIST (PUBLIC)
# ======================================================

@router.get("/companies")
def list_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).all()
    return [{"id": c.id, "name": c.name} for c in companies]

# ======================================================
# CURRENT USER (ME)
# ======================================================

@router.get("/me", response_model=AuthUser)
def get_me(current_user: AuthUser = Depends(get_current_user)):
    return current_user
