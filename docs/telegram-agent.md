# Telegram Agent Behaviour

This file documents how to customise the Telegram bot's AI assistant behaviour.
All prompts and intent logic live in `backend/app/services/telegram_ai.py`.

---

## How it works

When a linked user sends a plain-text message to the bot in a private chat, the pipeline is:

```
User message
    │
    ▼
_classify_intent()          ← LLM call with mode-specific system prompt
    │  Returns: {intent, query, title, description}
    ▼
handle_nl_message()         ← routes to the right executor
    │
    ├─ search_resource  →  _exec_search_resource()
    ├─ list_resources   →  _exec_list_resources()
    ├─ search_skill     →  _exec_search_skill()
    ├─ summarize_crisis →  _exec_summarize_crisis()
    ├─ create_request   →  _exec_create_request()
    └─ help / unknown   →  _help_text()
```

The LLM is only used for the classification step. All data retrieval and
response formatting is deterministic Python — the LLM never writes final replies.

---

## System prompts

Two system prompts control the agent's tone and intent priorities:

### `BLUE_SKY_SYSTEM` (normal mode)

```python
# backend/app/services/telegram_ai.py — line ~27
BLUE_SKY_SYSTEM = (
    "You are a friendly assistant for NeighbourGood, a community resource-sharing platform. "
    "Your community is in Blue Sky mode — everyday sharing of tools, skills, and time. "
    "Keep your tone warm and helpful. "
    "Classify the user message into exactly one intent and extract parameters. "
    "Respond with a single JSON object and no other text."
)
```

Customise this to:
- Change the persona name or voice ("formal", "casual", "multilingual-first")
- Emphasise certain intents over others
- Add context about your specific community

### `RED_SKY_SYSTEM` (crisis mode)

```python
# backend/app/services/telegram_ai.py — line ~35
RED_SKY_SYSTEM = (
    "You are an emergency coordination assistant for NeighbourGood in RED SKY (crisis) mode. "
    "The community is facing an active emergency. "
    "Be direct, clear, and calm — every second counts. "
    "Prioritise create_request and summarize_crisis intents when the message expresses urgency or need. "
    "Classify the user message into exactly one intent and extract parameters. "
    "Respond with a single JSON object and no other text."
)
```

Customise this to:
- Adjust urgency framing
- Add local emergency service context ("in a flood zone, treat 'need shelter' as critical")
- Change which intents are weighted higher

---

## Classification prompt

The user message is inserted into `_CLASSIFY_TEMPLATE`. The template defines
all available intents and their rules:

```python
_CLASSIFY_TEMPLATE = """Message: "{text}"

Respond with JSON matching this schema:
{
  "intent": "search_resource | list_resources | search_skill | summarize_crisis | create_request | help",
  "query": "<search term, or empty string>",
  "title": "<short title for new ticket, or empty string>",
  "description": "<detail for new ticket, or empty string>"
}

Intent rules:
- search_resource: user wants to borrow or find a specific item
- list_resources: user wants to see everything available
- search_skill: user needs help or someone with a skill
- summarize_crisis: user asks about open emergency tickets or what is happening
- create_request: user states an urgent need
- help: anything else or unclear
"""
```

### Adding a new intent

1. Add the intent name to the schema line in `_CLASSIFY_TEMPLATE`.
2. Add a rule line explaining when to use it.
3. Add an `_exec_<intent>()` function below the existing executors.
4. Add an `if intent == "<intent>":` branch in `handle_nl_message()`.
5. Add a test in `backend/tests/test_telegram_ai.py`.

Example — adding a `list_members` intent:

```python
# 1. In _CLASSIFY_TEMPLATE, extend the intent line:
"intent": "search_resource | list_resources | search_skill | summarize_crisis | create_request | list_members | help"

# 2. Add rule:
"- list_members: user wants to know who is in the community"

# 3. Add executor:
def _exec_list_members(community, db):
    if not community:
        return "You need to be in a community first."
    members = db.query(CommunityMember).filter(
        CommunityMember.community_id == community.id
    ).limit(10).all()
    ...

# 4. In handle_nl_message():
if intent == "list_members":
    return _exec_list_members(community, db)
```

---

## Fallback behaviour

When no AI provider is configured (`NG_AI_PROVIDER` unset), `_classify_intent()`
immediately returns `{"intent": "help"}` without any LLM call. The `_help_text()`
function then returns a list of slash commands.

To change what the fallback message says, edit `_help_text()`:

```python
def _help_text(ai_available: bool) -> str:
    if ai_available:
        intro = (
            "I didn't quite understand that. You can ask me things like:\n"
            '• "Do you have a ladder?"\n'
            ...
        )
    else:
        intro = "AI assistant is not configured. Use these commands:"
    ...
```

---

## Group chat behaviour

Group chat NL handling is intentionally minimal — the bot only responds to
crisis-keyword messages to avoid disrupting normal conversation:

```python
# backend/app/routers/telegram.py
if any(kw in lower for kw in ("crisis", "emergency", "ticket", "what's happening", "whats happening")):
    tg.send_message(chat_id, _exec_summarize_crisis(community, db))
```

To expand group chat responses, add keywords or call additional executors here.
To silence group chat NL responses entirely, remove this block.

---

## Reply formatting

All executor functions return HTML strings (Telegram's `parse_mode=HTML`).
Supported tags: `<b>bold</b>`, `<i>italic</i>`, `<code>code</code>`, `<a href="">link</a>`.

Use `&lt;` and `&gt;` for literal angle brackets in non-tag contexts.

---

## Configuration reference

| Variable | Default | Description |
|----------|---------|-------------|
| `NG_AI_PROVIDER` | unset | `ollama` or `openai`. Unset disables AI. |
| `NG_AI_BASE_URL` | `http://localhost:11434` | Base URL of the LLM API |
| `NG_AI_MODEL` | `llama3.2` | Model name passed to the API |
| `NG_AI_API_KEY` | unset | API key (required for OpenAI, optional for Ollama) |
| `NG_TELEGRAM_BOT_TOKEN` | unset | Bot token from BotFather |
| `NG_TELEGRAM_BOT_NAME` | unset | Bot username without `@` |
| `NG_TELEGRAM_WEBHOOK_SECRET` | unset | Secret for validating Telegram webhook calls |

All other Telegram and AI setup details are in [telegram-setup.md](telegram-setup.md).
