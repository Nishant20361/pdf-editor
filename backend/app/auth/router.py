"""Authentication router: register, login, logout, me, delete-account."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user_from_token, require_auth
from app.auth.security import (
    create_access_token,
    hash_password,
    validate_email_format,
    validate_password_strength,
    verify_password,
)
from app.config import settings
from app.db.database import get_db
from app.db.models import AuditEvent, Document, SessionToken, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ---- Request / Response schemas ----

class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    created_at: str
    document_count: int = 0
    storage_used_bytes: int = 0


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ---- Helper functions ----

def record_audit(
    db: Session,
    action: str,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Safely log an audit event."""
    try:
        event = AuditEvent(
            id=uuid.uuid4().hex,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details_json=details,
            ip_address=ip_address,
        )
        db.add(event)
        db.commit()
    except Exception as exc:
        logger.warning("Failed to record audit event: %s", exc)
        db.rollback()


def set_auth_cookie(response: Response, token: str) -> None:
    """Set secure HTTP-only cookie."""
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Clear the auth cookie."""
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )


# ---- Endpoints ----

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    response: Response,
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    """Register a new user account."""
    email = payload.email.strip().lower()

    if not validate_email_format(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format",
        )

    is_strong, err_msg = validate_password_strength(payload.password)
    if not is_strong:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )

    # Check existing user
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists",
        )

    pw_hash = hash_password(payload.password)
    user_id = uuid.uuid4().hex
    user = User(
        id=user_id,
        email=email,
        password_hash=pw_hash,
        is_active=True,
        is_verified=True,
        role="user",
    )
    db.add(user)

    # Create session token
    jti = uuid.uuid4().hex
    access_token = create_access_token({"sub": user.id, "email": user.email, "jti": jti})
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    session_token = SessionToken(
        id=uuid.uuid4().hex,
        user_id=user.id,
        token_hash=jti,
        expires_at=expires_at,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session_token)
    db.commit()
    db.refresh(user)

    record_audit(db, "register", user_id=user.id, resource_type="user", resource_id=user.id)
    set_auth_cookie(response, access_token)

    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            email=user.email,
            role=user.role,
            created_at=user.created_at.isoformat(),
            document_count=0,
            storage_used_bytes=0,
        ),
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    """Authenticate with email and password."""
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email, User.is_active == True).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Generate session & token
    jti = uuid.uuid4().hex
    access_token = create_access_token({"sub": user.id, "email": user.email, "jti": jti})
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    session_token = SessionToken(
        id=uuid.uuid4().hex,
        user_id=user.id,
        token_hash=jti,
        expires_at=expires_at,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session_token)
    db.commit()

    record_audit(db, "login", user_id=user.id, resource_type="user", resource_id=user.id)
    set_auth_cookie(response, access_token)

    # Calculate stats
    docs = db.query(Document).filter(Document.user_id == user.id).all()
    storage_bytes = sum(d.file_size for d in docs)

    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            email=user.email,
            role=user.role,
            created_at=user.created_at.isoformat(),
            document_count=len(docs),
            storage_used_bytes=storage_bytes,
        ),
    )


@router.post("/logout")
async def logout(
    response: Response,
    user: User = Depends(require_auth),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Log out of current session."""
    clear_auth_cookie(response)
    record_audit(db, "logout", user_id=user.id)
    return {"message": "Logged out successfully"}


@router.post("/logout-all")
async def logout_all(
    response: Response,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Revoke all active sessions for current user."""
    db.query(SessionToken).filter(SessionToken.user_id == user.id).update({"revoked": True})
    db.commit()
    clear_auth_cookie(response)
    record_audit(db, "logout_all", user_id=user.id)
    return {"message": "All sessions revoked successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Get current authenticated user info and usage stats."""
    docs = db.query(Document).filter(Document.user_id == user.id).all()
    storage_bytes = sum(d.file_size for d in docs)

    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        created_at=user.created_at.isoformat(),
        document_count=len(docs),
        storage_used_bytes=storage_bytes,
    )


@router.delete("/me")
async def delete_account(
    response: Response,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Delete current user account, all associated documents, and clean up files."""
    user_id = user.id
    # Clean up files for user's documents
    docs = db.query(Document).filter(Document.user_id == user_id).all()
    from app.services.file_service import delete_document
    for d in docs:
        try:
            delete_document(d.id)
        except Exception as exc:
            logger.warning("Error deleting doc %s on account removal: %s", d.id, exc)

    db.delete(user)
    db.commit()

    record_audit(db, "delete_account", user_id=user_id)
    clear_auth_cookie(response)
    return {"message": "Account and all associated documents deleted successfully"}
