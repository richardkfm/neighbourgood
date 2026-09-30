"""AI-powered natural language handler for the Telegram bot.

Classifies free-text messages from linked users into structured intents and
executes them against the database.  When the AI client is not configured,
falls back to a help message listing the available slash commands.
"""

import html
import json
import logging

from sqlalchemy.orm import Session

from app.models.community import Community, CommunityMember
from app.models.crisis import EmergencyTicket
from app.models.resource import Resource
from app.models.skill import Skill
from app.models.user import User
from app.services.activity import record_activity
from app.services.ai_client import get_ai_client
from app.services.webhooks import dispatch_event

logger = logging.getLogger(__name__)


def _e(value) -> str:
    """Escape user-controlled text for Telegram's HTML parse mode."""
    return html.escape(str(value), quote=False)

# ── Mode-aware system prompts ─────────────────────────────────────────────────
#
# Two distinct system prompts keep the agent's tone and available actions
# appropriate for the community's current state.  Customise these strings in
# TELEGRAM_AGENT.md (see project root) — the full guide explains every field.

BLUE_SKY_SYSTEM = (
    "You are a friendly assistant for NeighbourGood, a community resource-sharing platform. "
    "Your community is in Blue Sky mode — everyday sharing of tools, skills, and time. "
    "Keep your tone warm and helpful. "
    "Classify the user message into exactly one intent and extract parameters. "
    "Respond with a single JSON object and no other text."
)

RED_SKY_SYSTEM = (
    "You are an emergency coordination assistant for NeighbourGood in RED SKY (crisis) mode. "
    "The community is facing an active emergency. "
    "Be direct, clear, and calm — every second counts. "
    "Prioritise create_request and summarize_crisis intents when the message expresses urgency or need. "
    "Classify the user message into exactly one intent and extract parameters. "
    "Respond with a single JSON object and no other text."
)

_CLASSIFY_TEMPLATE = """Message: "{text}"

Respond with JSON matching this schema:
{{
  "intent": "search_resource | list_resources | search_skill | summarize_crisis | create_request | help",
  "query": "<search term, or empty string>",
  "title": "<short title for new ticket, or empty string>",
  "description": "<detail for new ticket, or empty string>"
}}

Intent rules:
- search_resource: user wants to borrow or find a specific item (e.g. "do you have a drill?")
- list_resources: user wants to see everything available (e.g. "what can I borrow?")
- search_skill: user needs help or someone with a skill (e.g. "who can fix my sink?")
- summarize_crisis: user asks about open emergency tickets or what is happening
- create_request: user states an urgent need (e.g. "I need food, the power is out")
- help: anything else or unclear
"""


def _classify_intent(text: str, community_mode: str) -> dict:
    """Call the LLM to classify the user message. Returns a dict with at least 'intent'."""
    client = get_ai_client()
    if not client:
        return {"intent": "help", "query": "", "title": "", "description": ""}

    system_prompt = RED_SKY_SYSTEM if community_mode == "red" else BLUE_SKY_SYSTEM
    prompt = _CLASSIFY_TEMPLATE.format(text=text[:500])
    raw = client.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        max_tokens=200,
    )
    if not raw:
        return {"intent": "help", "query": "", "title": "", "description": ""}

    try:
        # Strip markdown code fences if the model wraps the JSON
        cleaned = raw.strip().strip("```json").strip("```").strip()
        result = json.loads(cleaned)
        if "intent" not in result:
            return {"intent": "help", "query": "", "title": "", "description": ""}
        result.setdefault("query", "")
        result.setdefault("title", "")
        result.setdefault("description", "")
        return result
    except (json.JSONDecodeError, ValueError):
        logger.warning("telegram_ai: could not parse LLM response: %s", raw[:200])
        return {"intent": "help", "query": "", "title": "", "description": ""}


# ── Intent execution ──────────────────────────────────────────────────────────

def _exec_search_resource(query: str, community: Community | None, db: Session) -> str:
    if not community:
        return "You need to be in a community to search resources. Join one in the app."
    q = query.strip()
    filters = [
        Resource.community_id == community.id,
        Resource.is_available == True,  # noqa: E712
    ]
    if q:
        filters.append(Resource.title.ilike(f"%{q}%"))
    results = db.query(Resource).filter(*filters).limit(5).all()
    if not results:
        noun = f'matching "<b>{_e(q)}</b>"' if q else "available"
        return f"No resources {noun} in <b>{_e(community.name)}</b> right now."
    lines = [f"Resources in <b>{_e(community.name)}</b>:"]
    for r in results:
        cond = f" ({r.condition})" if r.condition else ""
        lines.append(f"• {_e(r.title)}{_e(cond)}")
    return "\n".join(lines)


def _exec_list_resources(community: Community | None, db: Session) -> str:
    return _exec_search_resource("", community, db)


def _exec_search_skill(query: str, community: Community | None, db: Session) -> str:
    if not community:
        return "You need to be in a community to search skills. Join one in the app."
    q = query.strip()
    filters = [
        Skill.community_id == community.id,
        Skill.skill_type == "offer",
    ]
    if q:
        filters.append(Skill.title.ilike(f"%{q}%"))
    results = db.query(Skill).filter(*filters).limit(5).all()
    if not results:
        noun = f'matching "<b>{_e(q)}</b>"' if q else "offered"
        return f"No skills {noun} in <b>{_e(community.name)}</b> right now."
    lines = [f"Skills offered in <b>{_e(community.name)}</b>:"]
    for s in results:
        lines.append(f"• {_e(s.title)} ({_e(s.category)})")
    return "\n".join(lines)


def _exec_summarize_crisis(community: Community | None, db: Session) -> str:
    if not community:
        return "You need to be in a community to view crisis tickets."
    if community.mode != "red":
        return f"<b>{_e(community.name)}</b> is in Blue Sky mode — no active crisis."
    tickets = (
        db.query(EmergencyTicket)
        .filter(
            EmergencyTicket.community_id == community.id,
            EmergencyTicket.status != "resolved",
        )
        .order_by(EmergencyTicket.created_at.desc())
        .limit(5)
        .all()
    )
    if not tickets:
        return f"No open emergency tickets in <b>{_e(community.name)}</b>."
    lines = [f"Open tickets in <b>{_e(community.name)}</b> (Red Sky):"]
    for t in tickets:
        lines.append(f"• [{t.urgency.upper()}] {_e(t.title)} ({t.ticket_type})")
    return "\n".join(lines)


def _exec_create_request(
    title: str, description: str, user: User, community: Community | None, db: Session
) -> str:
    if not community:
        return "You need to be in a community to create an emergency request."
    if community.mode != "red":
        return (
            f"<b>{_e(community.name)}</b> is in Blue Sky mode. "
            "Emergency requests can only be created during Red Sky (crisis) mode."
        )
    title = str(title or "")
    description = str(description or "")
    if not title.strip():
        return "Please describe what you need so I can create the request."
    ticket = EmergencyTicket(
        community_id=community.id,
        author_id=user.id,
        ticket_type="request",
        title=title[:300],
        description=description[:2000],
        status="open",
        urgency="high",
    )
    db.add(ticket)
    db.commit()
    record_activity(
        db,
        event_type="ticket_created",
        summary=f'created request ticket "{ticket.title}" (via Telegram)',
        actor_id=user.id,
        community_id=community.id,
    )
    dispatch_event(
        db,
        "ticket.created",
        {
            "title": ticket.title,
            "ticket_type": "request",
            "urgency": "high",
            "community_name": community.name,
        },
        [],
        community.id,
    )
    return (
        f"Emergency request created in <b>{_e(community.name)}</b>:\n"
        f"<b>{_e(ticket.title)}</b>\n"
        "Community leaders have been notified. Stay safe."
    )


def _help_text(ai_available: bool) -> str:
    if ai_available:
        intro = (
            "I didn't quite understand that. You can ask me things like:\n"
            '• "Do you have a ladder?"\n'
            '• "Who can help with plumbing?"\n'
            '• "What resources are available?"\n'
            '• "What emergency tickets are open?"\n\n'
            "Or use these slash commands:"
        )
    else:
        intro = "AI assistant is not configured. Use these commands:"
    return (
        f"{intro}\n"
        "/profile &lt;name&gt; — view member profile\n"
        "/lending &lt;name&gt; — see what someone is lending\n"
        "/skills &lt;name&gt; — see someone's offered skills"
    )


# ── Primary community helper ──────────────────────────────────────────────────

def get_primary_community(user: User, db: Session) -> Community | None:
    """Return the first active community the user belongs to, or None."""
    membership = (
        db.query(CommunityMember)
        .filter(CommunityMember.user_id == user.id)
        .first()
    )
    if not membership:
        return None
    return (
        db.query(Community)
        .filter(Community.id == membership.community_id, Community.is_active == True)  # noqa: E712
        .first()
    )


# ── Public entry point ────────────────────────────────────────────────────────

def handle_nl_message(
    text: str,
    user: User,
    community: Community | None,
    db: Session,
) -> str:
    """Classify *text* and execute the matched intent. Always returns a reply string."""
    ai_client = get_ai_client()
    community_mode = community.mode if community else "blue"

    intent_data = _classify_intent(text, community_mode)
    intent = intent_data.get("intent", "help")

    if intent == "search_resource":
        return _exec_search_resource(intent_data.get("query", ""), community, db)
    if intent == "list_resources":
        return _exec_list_resources(community, db)
    if intent == "search_skill":
        return _exec_search_skill(intent_data.get("query", ""), community, db)
    if intent == "summarize_crisis":
        return _exec_summarize_crisis(community, db)
    if intent == "create_request":
        return _exec_create_request(
            intent_data.get("title", text[:300]),
            intent_data.get("description", ""),
            user,
            community,
            db,
        )
    return _help_text(ai_available=ai_client is not None)
