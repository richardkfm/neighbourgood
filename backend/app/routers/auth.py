"""Authentication endpoints – register and login."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.csrf import generate_csrf_token
from app.middleware.rate_limit import _client_ip
from app.models.user import User
from app.schemas.auth import Token, UserLogin, UserRegister
from app.services.auth import hash_password, issue_token_for_user, verify_password
from app.services.lockout import check_lockout, clear_failures, record_failure

router = APIRouter(prefix="/auth", tags=["auth"])


class CsrfTokenOut(BaseModel):
    csrf_token: str


@router.get("/csrf-token", response_model=CsrfTokenOut)
def get_csrf_token():
    """Issue a CSRF token for use in the ``X-CSRF-Token`` request header.

    Browser clients that perform state-changing requests without a Bearer token
    (e.g. login/register forms) must obtain a token here and include it as the
    ``X-CSRF-Token`` header on every POST / PUT / PATCH / DELETE request.
    """
    return CsrfTokenOut(csrf_token=generate_csrf_token())


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(body: UserRegister, db: Session = Depends(get_db)):
    """Create a new user account and return a JWT token."""
    # Emails are case-insensitive: store and compare them lowercased.
    email = body.email.lower()
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name,
        neighbourhood=body.neighbourhood,
        language_code=body.language_code,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return Token(access_token=issue_token_for_user(user))


@router.post("/login", response_model=Token)
def login(body: UserLogin, request: Request, db: Session = Depends(get_db)):
    """Authenticate with email + password and return a JWT token.

    Returns a generic error for both unknown email and wrong password to
    prevent user-enumeration attacks (Phase 4b hardening).
    """
    # Lockout is keyed by (email, client IP) so a third party cannot lock a
    # known email out of its owner's own network.
    client_ip = _client_ip(request)
    is_locked, retry_after = check_lockout(body.email, client_ip)
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked due to too many failed login attempts. "
                   f"Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.query(User).filter(func.lower(User.email) == body.email.lower()).first()

    # Unified failure path — do not distinguish "no such user" from "wrong password"
    if not user or not verify_password(body.password, user.hashed_password):
        record_failure(body.email, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    clear_failures(body.email, client_ip)
    return Token(access_token=issue_token_for_user(user))
