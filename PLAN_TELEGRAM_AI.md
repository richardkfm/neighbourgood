# Plan: Telegram NL Interface (AI-powered)

## Goal

Extend the existing Telegram bot webhook so that linked users can send **natural language messages**
and receive useful responses — searching resources, listing skills, summarizing crisis tickets, and
posting emergency requests — all without opening the app.

When AI is not configured, the bot falls back gracefully to a plain-text help message.

---

## What Already Exists

- `app/services/telegram.py` — `send_message()`, `is_configured()`
- `app/routers/telegram.py` — webhook at `POST /telegram/webhook`; handles `/start`, `/link`,
  `/profile`, `/lending`, `/skills` slash commands; **ignores all non-command text**
- `app/services/ai_client.py` — generic OpenAI-compatible LLM wrapper (reuse as-is)
- `User.telegram_chat_id` — stored on the User model; we can look users up by chat_id

---

## New Files

### `backend/app/services/telegram_ai.py`

Handles the NL pipeline:

1. **`classify_intent(text, context_summary) -> dict`**
   Calls the LLM with a structured prompt listing supported intents:
   - `search_resource` + `query` param
   - `list_resources` (all available in community)
   - `search_skill` + `query` param
   - `summarize_crisis` (Red Sky tickets summary)
   - `create_request` + `title` + `description` (posts EmergencyTicket of type `request`)
   - `help` / `unknown`

2. **`execute_intent(intent, user, community, db) -> str`**
   Runs the DB query for the intent and formats a Telegram-safe HTML reply.

3. **`handle_nl_message(text, user, community, db) -> str`**
   Orchestrates classify → execute. Falls back to help text if AI unavailable or intent unknown.

---

## Modified File

### `backend/app/routers/telegram.py`

In `telegram_webhook`, after the existing slash-command blocks, add:

```python
# ── Natural language messages (personal chats only) ────────────
if chat_type == "private":
    user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if user:
        community = _get_primary_community(user, db)
        reply = handle_nl_message(text, user, community, db)
        tg.send_message(chat_id, reply)
return {"ok": True}
```

Also handle non-command text in **linked group chats** for crisis summaries:

```python
if chat_type in ("group", "supergroup") and not text.startswith("/"):
    community = db.query(Community).filter(Community.telegram_group_id == chat_id).first()
    if community:
        # AI-assisted group queries scoped to this community
        ...
```

Helper `_get_primary_community(user, db)` — returns the first active community the user belongs to
(we already have the join table).

---

## Implementation Steps

1. **`backend/app/services/telegram_ai.py`** — new service
   - `classify_intent()` using `AIClient` from `app.services.ai_client`
   - `execute_intent()` with DB queries for each intent type
   - `handle_nl_message()` orchestrator
   - Graceful no-AI fallback returns a formatted help string listing slash commands

2. **`backend/app/routers/telegram.py`** — extend webhook
   - Import `handle_nl_message` from the new service
   - Add private-chat NL handler block
   - Add group-chat NL handler block (crisis summary only, scoped to community)

3. **`backend/tests/test_telegram_ai.py`** — new test file
   - `test_nl_search_resource` — linked user sends "do you have a ladder?"
   - `test_nl_search_skill` — "who can help me with plumbing?"
   - `test_nl_create_request` — "I need food, we have no power"
   - `test_nl_summarize_crisis` — "what emergency tickets are open?"
   - `test_nl_unknown_fallback` — garbage text returns help message
   - `test_nl_unlinked_user` — unlinked chat_id is silently ignored
   - `test_nl_no_ai_fallback` — AI not configured → returns slash-command help text

---

## Scope

- No new models or Alembic migrations needed (`telegram_chat_id` already on User,
  `telegram_group_id` already on Community)
- No new API endpoints
- No frontend changes
- AI is optional: all intents have a rule-based fallback or help-text response
- `create_request` only works in Red Sky communities (guard in `execute_intent`)
