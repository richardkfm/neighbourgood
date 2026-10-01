"""Shared dependencies for route handlers."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.auth import decode_access_token_claims

security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    claims = decode_access_token_claims(credentials.credentials)
    if claims is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id, version = claims
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if version != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    _apply_admin_emails(user, db)
    return user


def _apply_admin_emails(user: User, db: Session) -> None:
    """Grant the platform admin role to accounts listed in NG_ADMIN_EMAILS.

    Only ever promotes: removing an email from the list does not demote an
    admin, so roles granted by other means are left alone.
    """
    if user.role == "admin" or not settings.admin_emails:
        return
    if user.email.lower() in {e.strip().lower() for e in settings.admin_emails}:
        user.role = "admin"
        db.commit()


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_optional),
    db: Session = Depends(get_db),
) -> User | None:
    """Optional authentication dependency. Returns None if no valid token provided."""
    if credentials is None:
        return None
    try:
        claims = decode_access_token_claims(credentials.credentials)
        if claims is None:
            return None
        user_id, version = claims
        user = db.query(User).filter(User.id == user_id).first()
        if user is None or not user.is_active or version != user.token_version:
            return None
        return user
    except Exception:
        return None
