"""Generic outbound webhook CRUD endpoints."""

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.webhook import Webhook
from app.schemas.webhook import WEBHOOK_EVENTS, WebhookCreate, WebhookOut
from app.utils.net import is_safe_url

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("", response_model=list[WebhookOut])
def list_webhooks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List webhooks registered by the current user."""
    hooks = (
        db.query(Webhook)
        .filter(Webhook.owner_type == "user", Webhook.owner_id == current_user.id)
        .order_by(Webhook.created_at.desc())
        .all()
    )
    return [WebhookOut.from_orm_model(h) for h in hooks]


@router.post("", response_model=WebhookOut, status_code=status.HTTP_201_CREATED)
def create_webhook(
    body: WebhookCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register a new outbound webhook URL."""
    invalid = [e for e in body.event_types if e not in WEBHOOK_EVENTS]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown event types: {invalid}. Valid: {WEBHOOK_EVENTS}",
        )
    if not body.event_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="event_types must not be empty",
        )

    if not is_safe_url(body.url, allow_private=settings.webhook_allow_private):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Webhook URL must be an http(s) address that resolves to a public host",
        )

    hook = Webhook(
        owner_type="user",
        owner_id=current_user.id,
        url=body.url,
        secret=body.secret,
        event_types=json.dumps(body.event_types),
    )
    db.add(hook)
    db.commit()
    db.refresh(hook)
    return WebhookOut.from_orm_model(hook)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    webhook_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a webhook (owner only)."""
    hook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not hook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    if hook.owner_type != "user" or hook.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your webhook")
    db.delete(hook)
    db.commit()
