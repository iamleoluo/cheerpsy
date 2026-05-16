import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import RequireRole, get_current_user
from app.auth.jwt import create_access_token
from app.auth.password import hash_password, verify_password
from app.database import get_db
from app.models.invitation import Invitation
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.services.audit import write_audit

router = APIRouter(prefix="/auth", tags=["auth"])

INVITE_EXPIRY_HOURS = 72


def _generate_key() -> str:
    parts = [secrets.token_hex(2).upper() for _ in range(3)]
    return f"CHEER-{parts[0]}-{parts[1]}-{parts[2]}"


# ── Login ──────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    token = create_access_token({"sub": str(user.id), "role": user.role, "name": user.name})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.get("/therapists", response_model=list[UserResponse])
def list_therapists(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(User).filter(User.role == "therapist", User.is_active == True).order_by(User.name).all()


# ── User management (admin) ───────────────────────────

class UserListResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    user_code: str | None = None
    commission_rate: float | None = None
    is_active: bool
    model_config = {"from_attributes": True}


@router.get("/users", response_model=list[UserListResponse])
def list_users(user: User = Depends(RequireRole(["admin"])), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.role, User.name).all()


@router.put("/users/{user_id}/toggle")
def toggle_user(user_id: int, user: User = Depends(RequireRole(["admin"])), db: Session = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    before_active = target.is_active
    target.is_active = not target.is_active
    write_audit(db, "users", target.id, "UPDATE", user.id,
                {"is_active": before_active}, {"is_active": target.is_active})
    db.commit()
    return {"id": target.id, "is_active": target.is_active}


class CommissionRateRequest(BaseModel):
    commission_rate: float


@router.put("/users/{user_id}/commission-rate")
def set_commission_rate(
    user_id: int,
    body: CommissionRateRequest,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role != "therapist":
        raise HTTPException(status_code=400, detail="Commission rate only applies to therapists")
    if not (0 < body.commission_rate <= 1):
        raise HTTPException(status_code=400, detail="Commission rate must be between 0 and 1")
    old_rate = float(target.commission_rate) if target.commission_rate is not None else None
    target.commission_rate = body.commission_rate
    write_audit(db, "users", target.id, "UPDATE", user.id,
                {"commission_rate": old_rate}, {"commission_rate": body.commission_rate})
    db.commit()
    return {"id": target.id, "commission_rate": float(target.commission_rate)}


# ── Invitations (admin) ───────────────────────────────

ROLE_CODE_PREFIX = {"admin": "A", "accountant": "C", "staff": "S", "therapist": "T"}


class CreateInviteRequest(BaseModel):
    name: str
    role: str  # therapist | accountant | admin | staff
    user_code: str | None = None


class InvitationResponse(BaseModel):
    id: int
    invite_key: str
    type: str
    name: str
    role: str | None = None
    user_code: str | None = None
    target_user_id: int | None = None
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None
    model_config = {"from_attributes": True}


@router.post("/invitations", response_model=InvitationResponse)
def create_invitation(
    body: CreateInviteRequest,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    if body.role not in ("therapist", "accountant", "admin", "staff"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if not body.user_code:
        raise HTTPException(status_code=400, detail="User code required for all roles")
    existing = db.query(User).filter(User.user_code == body.user_code, User.is_active == True).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"User code '{body.user_code}' already in use by active user")

    inv = Invitation(
        invite_key=_generate_key(),
        type="invite",
        name=body.name,
        role=body.role,
        user_code=body.user_code,
        created_by=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=INVITE_EXPIRY_HOURS),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.get("/invitations", response_model=list[InvitationResponse])
def list_invitations(user: User = Depends(RequireRole(["admin"])), db: Session = Depends(get_db)):
    return db.query(Invitation).order_by(Invitation.created_at.desc()).all()


@router.post("/reset-key/{user_id}", response_model=InvitationResponse)
def create_reset_key(
    user_id: int,
    user: User = Depends(RequireRole(["admin"])),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    inv = Invitation(
        invite_key=_generate_key(),
        type="reset",
        name=target.name,
        target_user_id=target.id,
        created_by=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=INVITE_EXPIRY_HOURS),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


# ── Public: verify key / register / reset ──────────────

class InviteVerifyResponse(BaseModel):
    name: str
    role: str | None = None
    type: str


@router.get("/invite/{key}", response_model=InviteVerifyResponse)
def verify_invite(key: str, db: Session = Depends(get_db)):
    inv = db.query(Invitation).filter(Invitation.invite_key == key).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invalid key")
    if inv.used_at:
        raise HTTPException(status_code=400, detail="Key already used")
    if inv.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Key expired")
    return InviteVerifyResponse(name=inv.name, role=inv.role, type=inv.type)


class RegisterRequest(BaseModel):
    invite_key: str
    email: str
    password: str


@router.post("/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    inv = db.query(Invitation).filter(Invitation.invite_key == body.invite_key).first()
    if not inv or inv.used_at or inv.type != "invite":
        raise HTTPException(status_code=400, detail="Invalid or expired invitation key")
    if inv.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation key expired")

    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Clear user_code from deactivated user so UNIQUE constraint allows reuse
    if inv.user_code:
        old_user = db.query(User).filter(
            User.user_code == inv.user_code,
            User.is_active == False,
        ).first()
        if old_user:
            old_user.user_code = None

    new_user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=inv.name,
        role=inv.role,
        user_code=inv.user_code,
        is_active=True,
    )
    db.add(new_user)
    db.flush()
    inv.used_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Account created", "name": inv.name}


class ResetPasswordRequest(BaseModel):
    invite_key: str
    password: str


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    inv = db.query(Invitation).filter(Invitation.invite_key == body.invite_key).first()
    if not inv or inv.used_at or inv.type != "reset":
        raise HTTPException(status_code=400, detail="Invalid or expired reset key")
    if inv.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset key expired")

    target = db.query(User).filter(User.id == inv.target_user_id).first()
    if not target:
        raise HTTPException(status_code=400, detail="User not found")

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    target.password_hash = hash_password(body.password)
    inv.used_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Password updated", "name": target.name}
