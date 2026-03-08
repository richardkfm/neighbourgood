"""Telegram bot webhook receiver and account-linking endpoints."""

import datetime
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.community import Community, CommunityMember
from app.models.resource import Resource
from app.models.skill import Skill
from app.models.user import User
from app.models.webhook import TelegramLinkToken
from app.schemas.webhook import TelegramGroupLinkStart, TelegramLinkStart
from app.services import telegram as tg
from app.services.telegram_ai import get_primary_community, handle_nl_message

router = APIRouter(tags=["telegram"])


# ── User linking ──────────────────────────────────────────────────


@router.post("/users/me/telegram/start-link", response_model=TelegramLinkStart)
def start_telegram_link(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a one-time deep-link URL so the user can link their Telegram account."""
    if not tg.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram integration is not configured on this instance",
        )
    token = secrets.token_urlsafe(32)
    expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)

    # Invalidate any existing unused token for this user
    db.query(TelegramLinkToken).filter(
        TelegramLinkToken.token_type == "user",
        TelegramLinkToken.owner_id == current_user.id,
        TelegramLinkToken.used == False,  # noqa: E712
    ).delete()

    link_token = TelegramLinkToken(
        token=token,
        token_type="user",
        owner_id=current_user.id,
        expires_at=expires,
    )
    db.add(link_token)
    db.commit()

    bot_name = settings.telegram_bot_name
    return TelegramLinkStart(bot_url=f"https://t.me/{bot_name}?start={token}")


@router.delete("/users/me/telegram", status_code=status.HTTP_204_NO_CONTENT)
def unlink_telegram(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unlink Telegram from the current user's account."""
    current_user.telegram_chat_id = None
    db.commit()


# ── Community group linking ───────────────────────────────────────


def _require_admin_or_leader(db: Session, community_id: int, user_id: int) -> CommunityMember:
    membership = (
        db.query(CommunityMember)
        .filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member")
    if membership.role not in ("admin", "leader"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin or leader access required"
        )
    return membership


@router.post(
    "/communities/{community_id}/telegram/start-link",
    response_model=TelegramGroupLinkStart,
)
def start_community_telegram_link(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a one-time token so a community admin can link a Telegram group.

    1. Admin calls this endpoint to get a token.
    2. Admin adds the bot to the Telegram group.
    3. Admin types /link {token} in the group.
    4. Bot webhook receives the command, validates the token, and stores the group chat_id.
    """
    if not tg.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram integration is not configured on this instance",
        )
    community = db.query(Community).filter(Community.id == community_id).first()
    if not community or not community.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found")
    _require_admin_or_leader(db, community_id, current_user.id)

    token = secrets.token_urlsafe(24)
    expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=30)

    db.query(TelegramLinkToken).filter(
        TelegramLinkToken.token_type == "community",
        TelegramLinkToken.owner_id == community_id,
        TelegramLinkToken.used == False,  # noqa: E712
    ).delete()

    link_token = TelegramLinkToken(
        token=token,
        token_type="community",
        owner_id=community_id,
        expires_at=expires,
    )
    db.add(link_token)
    db.commit()

    return TelegramGroupLinkStart(token=token)


@router.delete(
    "/communities/{community_id}/telegram",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unlink_community_telegram(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unlink Telegram group from a community (admin only)."""
    community = db.query(Community).filter(Community.id == community_id).first()
    if not community or not community.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found")
    _require_admin_or_leader(db, community_id, current_user.id)
    community.telegram_group_id = None
    db.commit()


# ── Telegram bot webhook ──────────────────────────────────────────


@router.post("/telegram/webhook", status_code=status.HTTP_200_OK)
async def telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """Receive bot updates from Telegram (set via Telegram's setWebhook API).

    Handles:
    - /start {token}  → link a user's personal account
    - /link {token}   → link a community group (sent inside a group)
    - /profile {name}, /lending {name}, /skills {name}  → community member lookup
    """
    # Validate secret header if configured
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid secret")

    body = await request.json()
    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = str(message.get("chat", {}).get("id", ""))
    text: str = message.get("text", "")
    chat_type = message.get("chat", {}).get("type", "private")

    # ── Natural language messages (private chats from linked users) ──────────
    if not text.startswith("/"):
        if chat_type == "private":
            user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
            if user:
                community = get_primary_community(user, db)
                reply = handle_nl_message(text, user, community, db)
                tg.send_message(chat_id, reply)
        elif chat_type in ("group", "supergroup"):
            community = (
                db.query(Community).filter(Community.telegram_group_id == chat_id).first()
            )
            if community:
                # In group chats, only handle crisis summary queries for linked communities
                lower = text.lower()
                if any(kw in lower for kw in ("crisis", "emergency", "ticket", "what's happening", "whats happening")):
                    from app.services.telegram_ai import _exec_summarize_crisis
                    tg.send_message(chat_id, _exec_summarize_crisis(community, db))
        return {"ok": True}

    # Strip bot mention suffix (e.g. /start@BotName)
    command_part = text.split()[0].split("@")[0]
    args = text.split()[1:]

    # ── /start {token} — personal account linking ────────────────
    if command_part == "/start" and args:
        token_str = args[0]
        link_token = (
            db.query(TelegramLinkToken)
            .filter(
                TelegramLinkToken.token == token_str,
                TelegramLinkToken.token_type == "user",
                TelegramLinkToken.used == False,  # noqa: E712
                TelegramLinkToken.expires_at > datetime.datetime.utcnow(),
            )
            .first()
        )
        if not link_token:
            tg.send_message(chat_id, "Link expired or invalid. Please request a new link from the app.")
            return {"ok": True}
        user = db.query(User).filter(User.id == link_token.owner_id).first()
        if user:
            user.telegram_chat_id = chat_id
            link_token.used = True
            db.commit()
            tg.send_message(
                chat_id,
                f"Your NeighbourGood account (<b>{user.display_name}</b>) is now linked!\n"
                "You'll receive notifications for messages, bookings, and community events here.",
            )
        return {"ok": True}

    # ── /link {token} — community group linking ──────────────────
    if command_part == "/link" and args and chat_type in ("group", "supergroup"):
        token_str = args[0]
        link_token = (
            db.query(TelegramLinkToken)
            .filter(
                TelegramLinkToken.token == token_str,
                TelegramLinkToken.token_type == "community",
                TelegramLinkToken.used == False,  # noqa: E712
                TelegramLinkToken.expires_at > datetime.datetime.utcnow(),
            )
            .first()
        )
        if not link_token:
            tg.send_message(chat_id, "Link token expired or invalid. Generate a new one in the app.")
            return {"ok": True}
        community = db.query(Community).filter(Community.id == link_token.owner_id).first()
        if community:
            community.telegram_group_id = chat_id
            link_token.used = True
            db.commit()
            tg.send_message(
                chat_id,
                f"This group is now linked to <b>{community.name}</b> on NeighbourGood!\n"
                "Community announcements will be posted here.",
            )
        return {"ok": True}

    # ── Bot commands: /profile, /lending, /skills ─────────────────
    if command_part in ("/profile", "/lending", "/skills") and chat_type in ("group", "supergroup"):
        community = (
            db.query(Community)
            .filter(Community.telegram_group_id == chat_id)
            .first()
        )
        if not community:
            return {"ok": True}

        name_query = " ".join(args).strip() if args else ""
        if not name_query:
            tg.send_message(chat_id, f"Usage: {command_part} &lt;name&gt;")
            return {"ok": True}

        # Find members of this community whose display_name matches
        member_ids = [
            row[0]
            for row in db.query(CommunityMember.user_id)
            .filter(CommunityMember.community_id == community.id)
            .all()
        ]
        matching_users = (
            db.query(User)
            .filter(
                User.id.in_(member_ids),
                User.display_name.ilike(f"%{name_query}%"),
                User.is_active == True,  # noqa: E712
            )
            .all()
        )

        if not matching_users:
            tg.send_message(
                chat_id,
                f"No members found matching '<b>{name_query}</b>' in {community.name}.",
            )
            return {"ok": True}

        lines = []
        for u in matching_users[:3]:  # cap at 3 results
            parts = [f"<b>{u.display_name}</b>"]

            if command_part in ("/profile", "/lending"):
                resources = (
                    db.query(Resource)
                    .filter(
                        Resource.owner_id == u.id,
                        Resource.community_id == community.id,
                        Resource.is_available == True,  # noqa: E712
                    )
                    .all()
                )
                if resources:
                    titles = ", ".join(r.title for r in resources[:5])
                    parts.append(f"  Lending: {titles}")
                elif command_part == "/lending":
                    parts.append("  No items currently available")

            if command_part in ("/profile", "/skills"):
                skills = (
                    db.query(Skill)
                    .filter(
                        Skill.owner_id == u.id,
                        Skill.community_id == community.id,
                        Skill.skill_type == "offer",
                    )
                    .all()
                )
                if skills:
                    skill_list = ", ".join(f"{s.title} ({s.category})" for s in skills[:5])
                    parts.append(f"  Skills: {skill_list}")
                elif command_part == "/skills":
                    parts.append("  No skills listed")

            lines.append("\n".join(parts))

        tg.send_message(chat_id, "\n\n".join(lines))
        return {"ok": True}

    return {"ok": True}
