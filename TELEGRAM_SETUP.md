# Telegram Bot Setup

NeighbourGood includes a Telegram bot that lets community members interact with the platform directly from Telegram — no app required. It supports personal notifications, community group announcements, slash commands, and an AI-powered natural language interface.

---

## 1. Create a bot with BotFather

Open a conversation with [@BotFather](https://t.me/BotFather) and run:

```
/newbot
```

Follow the prompts to choose a name and username (e.g. `MyNeighbourhoodBot`). Copy the **API token** you receive — you'll need it in the next step.

---

## 2. Configure environment variables

Add the following to your `.env` file (or Docker environment):

```env
# Required
NG_TELEGRAM_BOT_TOKEN=123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NG_TELEGRAM_BOT_NAME=your_bot_username     # without the @ prefix

# Optional — the webhook is always protected by a secret. When this is unset,
# one is derived from NG_SECRET_KEY and the bot token.
# NG_TELEGRAM_WEBHOOK_SECRET=some-random-string-at-least-32-chars

# Needed for automatic webhook registration (public HTTPS URL of the backend)
NG_INSTANCE_URL=https://your-domain
```

Telegram updates without the matching `X-Telegram-Bot-Api-Secret-Token` header are rejected with `403`. If you set your own secret, generate a strong one with `openssl rand -hex 32`.

---

## 3. Register the webhook with Telegram

After the backend is running and publicly reachable, register the webhook once. As a platform admin (see `NG_ADMIN_EMAILS`), call:

```bash
curl -X POST "https://<your-domain>/telegram/webhook/register" \
  -H "Authorization: Bearer <your access token>"
```

This registers `NG_INSTANCE_URL/telegram/webhook` together with the webhook secret (explicit or derived), so you never have to copy the secret around.

If you set `NG_TELEGRAM_WEBHOOK_SECRET` yourself you can also register manually:

```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://<your-domain>/telegram/webhook" \
  -d "secret_token=<NG_TELEGRAM_WEBHOOK_SECRET>"
```

**Upgrading from 2.2 or earlier:** webhooks registered without a secret stop working, because unauthenticated updates are now rejected. Register the webhook again once using either method above.

Replace `<your-domain>` with the public HTTPS URL of your NeighbourGood instance. For local development use a tunnel such as [ngrok](https://ngrok.com/) or [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).

---

## 4. Link accounts

### Personal notifications

Users go to **Settings → Telegram** and click the link button. This generates a one-time deep link (`t.me/your_bot?start=TOKEN`) that lets the bot identify them and store their Telegram chat ID. Notifications for messages, bookings, and community events are then sent directly to their Telegram.

### Community group chat

A community admin:

1. Adds the bot to the Telegram group.
2. Goes to **Settings → Telegram** (community section) and copies the generated link token.
3. Types `/link <token>` in the group.

The bot then recognises the group and sends community-wide announcements there.

---

## 5. Slash commands

These commands work in any linked group chat:

| Command | Description |
|---------|-------------|
| `/profile <name>` | Show a neighbour's reputation score and community role |
| `/lending <name>` | List resources a neighbour currently has available to borrow |
| `/skills <name>` | List skills a neighbour is offering |

---

## 6. AI natural language interface

When AI is configured (see below), users who have linked their personal account can send **plain text messages** to the bot in a private chat and get useful responses without any slash commands.

### What you can say (Blue Sky mode)

| Example message | What the bot does |
|----------------|-------------------|
| "Do you have a ladder?" | Searches available resources for "ladder" |
| "Who can help with plumbing?" | Searches skill offers for "plumbing" |
| "What can I borrow?" | Lists all resources currently available |
| "Show me what's available" | Lists all resources currently available |

### What you can say (Red Sky / crisis mode)

Everything above, plus:

| Example message | What the bot does |
|----------------|-------------------|
| "What emergency tickets are open?" | Lists all open crisis tickets with urgency levels |
| "What's happening?" | Summarises the current crisis situation |
| "I need food, we have no power" | Creates an emergency request ticket (type: request, urgency: high) |
| "We have spare blankets to offer" | Will prompt you to create a ticket via the app (offer tickets require more detail) |

### What the bot will NOT do

- It will not post on your behalf without clear intent (it always confirms actions like ticket creation).
- It will not create emergency requests in Blue Sky mode — the community must be in Red Sky first.
- It will not access information from other communities you don't belong to.
- It will not send messages to other users on your behalf.
- It will not perform admin actions (toggling crisis mode, assigning leaders, etc.).
- It will not reveal other users' private information (email, location, chat ID).

### Group chat behaviour

In linked group chats, the bot only responds to:
- Slash commands (`/profile`, `/lending`, `/skills`, `/link`)
- Messages containing crisis-related keywords (`crisis`, `emergency`, `ticket`, `what's happening`) — these trigger an automatic crisis summary

All other group chat messages are ignored so the bot does not disrupt normal conversation.

---

## 7. Setting up local AI

The AI features (natural language understanding, matching re-ranking) use an OpenAI-compatible API. You can run one locally with [Ollama](https://ollama.com/) — no internet or API key required.

### Install Ollama

```bash
# Linux / macOS
curl -fsSL https://ollama.com/install.sh | sh

# Or with Docker
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
```

### Recommended models

All three are small enough to run on a laptop without a GPU (CPU inference, 4–8 GB RAM):

| Model | Size | Best for | Pull command |
|-------|------|----------|--------------|
| **Llama 3.2 3B** *(default)* | ~2 GB | Fast responses, good instruction following, works well for JSON classification | `ollama pull llama3.2` |
| **Phi-4 Mini** | ~2.5 GB | Excellent at structured tasks and JSON output, very low hallucination rate | `ollama pull phi4-mini` |
| **Mistral 7B** | ~4 GB | Higher quality reasoning, better for nuanced intent classification | `ollama pull mistral` |

**Recommendation:** Start with `llama3.2` (it's the configured default). Switch to `phi4-mini` if you see JSON parsing errors, or to `mistral` if you want better understanding of complex or multilingual messages.

### Configure NeighbourGood to use Ollama

Add to your `.env`:

```env
NG_AI_PROVIDER=ollama
NG_AI_BASE_URL=http://localhost:11434
NG_AI_MODEL=llama3.2
# NG_AI_API_KEY is not needed for Ollama
```

If Ollama is running in Docker alongside the backend, use the service name instead of `localhost`:

```env
NG_AI_BASE_URL=http://ollama:11434
```

### Using OpenAI instead

```env
NG_AI_PROVIDER=openai
NG_AI_BASE_URL=https://api.openai.com
NG_AI_MODEL=gpt-4o-mini
NG_AI_API_KEY=sk-...
```

`gpt-4o-mini` is cheap, fast, and produces reliable JSON — a good choice if you prefer a managed service.

### Verifying AI is working

```bash
curl http://localhost:8300/matching/status
# {"ai_available": true, "provider": "ollama", "model": "llama3.2"}
```

If `ai_available` is `false`, check that `NG_AI_PROVIDER` is set and Ollama is running.

---

## 8. Events sent to Telegram

| Event | Personal chat | Community group |
|-------|--------------|----------------|
| New message received | ✓ | — |
| Booking created (owner) | ✓ | — |
| Booking status changed (borrower) | ✓ | — |
| New resource shared | — | ✓ (all modes) |
| New skill posted | — | ✓ (all modes) |
| Member joined | — | ✓ (all modes) |
| Emergency ticket created | ✓ | ✓ (Red Sky only) |
| Crisis mode changed | ✓ (all members) | — |

---

## 9. Webhooks (generic integrations)

Any external service can receive the same events via **Settings → Webhooks**. POST requests are signed with `X-Signature: sha256=<hmac>` using the secret you provide. This lets you forward events to Discord, Slack, n8n, Zapier, or any HTTP endpoint.
