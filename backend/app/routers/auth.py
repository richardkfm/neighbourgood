"""Authentication endpoints – register, login and password reset."""

import datetime
import hashlib
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.csrf import generate_csrf_token
from app.middleware.rate_limit import _client_ip
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.schemas.auth import (
    MessageOut,
    PasswordResetConfirm,
    PasswordResetRequest,
    Token,
    UserLogin,
    UserRegister,
)
from app.services.auth import hash_password, issue_token_for_user, verify_password
from app.services.lockout import check_lockout, clear_all_failures_for_email, clear_failures, record_failure
from app.services.notifications import notify_password_reset

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


# ── Password reset ─────────────────────────────────────────────────

PASSWORD_RESET_TTL = datetime.timedelta(hours=1)
_RESET_REQUEST_DETAIL = "If an account with that email exists, a password reset link has been sent."


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _utcnow() -> datetime.datetime:
    """Naive UTC, matching how the database stores timestamps."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


@router.post(
    "/password-reset/request",
    response_model=MessageOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    body: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Email a single-use password reset link.

    Always answers 202 with the same body whether or not the email belongs to
    an account, so the endpoint cannot be used to enumerate users.
    """
    user = (
        db.query(User)
        .filter(func.lower(User.email) == body.email.lower(), User.is_active == True)  # noqa: E712
        .first()
    )
    if user:
        now = _utcnow()
        # A new request supersedes any link that is still outstanding.
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ).update({PasswordResetToken.used_at: now}, synchronize_session=False)

        raw_token = secrets.token_urlsafe(32)
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_reset_token(raw_token),
                expires_at=now + PASSWORD_RESET_TTL,
            )
        )
        db.commit()
        # Sent after the response so response time does not reveal whether the account exists.
        background_tasks.add_task(notify_password_reset, user.email, raw_token)

    return MessageOut(detail=_RESET_REQUEST_DETAIL)


@router.post("/password-reset/confirm", response_model=MessageOut)
def confirm_password_reset(body: PasswordResetConfirm, db: Session = Depends(get_db)):
    """Set a new password using a token from the reset email. Each token works once."""
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token"
    )
    now = _utcnow()
    record = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == _hash_reset_token(body.token))
        .first()
    )
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise invalid
    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None or not user.is_active:
        raise invalid

    # Atomically claim the token so two concurrent confirms cannot both succeed.
    claimed = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.id == record.id, PasswordResetToken.used_at.is_(None))
        .update({PasswordResetToken.used_at: now}, synchronize_session=False)
    )
    if claimed != 1:
        db.rollback()
        raise invalid

    user.hashed_password = hash_password(body.new_password)
    # Sign out every session issued before the reset
    user.token_version += 1
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({PasswordResetToken.used_at: now}, synchronize_session=False)
    db.commit()

    clear_all_failures_for_email(user.email)
    return MessageOut(detail="Password has been reset")
