# Configuration

NeighbourGood is configured with environment variables, all prefixed `NG_`. Put them in `.env` in the project root (start from [`.env.example`](../.env.example)); Docker Compose passes them to the backend. Restart the backend after changing them.

## Essentials

| Variable | Default | Notes |
|----------|---------|-------|
| `NG_SECRET_KEY` | none (the built-in default is rejected) | **Required in production.** Signs login tokens; at least 32 characters. Generate with `openssl rand -hex 32`. Changing it logs everyone out |
| `NG_DATABASE_URL` | `sqlite:///./neighbourgood.db` | Docker Compose sets a PostgreSQL URL; SQLite is for local development |
| `NG_DEBUG` | `false` | `true` only for local development: accepts the default secret key, relaxes HSTS, CSP and CSRF. Never in production |
| `NG_ADMIN_EMAILS` | `[]` | JSON array. Accounts with these emails become platform admins on their next request |
| `NG_FRONTEND_URL` | `http://localhost:3800` | Public URL of the web app, used in email links |
| `NG_CORS_ORIGINS` | `["http://localhost:3800","http://localhost:5173"]` | JSON array of allowed browser origins; set it to your public URL |

## Crisis mode

| Variable | Default | Notes |
|----------|---------|-------|
| `NG_PLATFORM_MODE` | `blue` | `red` puts **every** community on the instance into Red Sky. Each community keeps its own setting and returns to it when the instance is set back to `blue`. Communities can also switch individually (admin toggle or 60 % vote) |

## Instance identity (federation)

Shown at `/instance/info` and in other instances' directories.

| Variable | Example |
|----------|---------|
| `NG_INSTANCE_NAME` | `My NeighbourGood` |
| `NG_INSTANCE_DESCRIPTION` | `A neighbourhood resource-sharing community` |
| `NG_INSTANCE_REGION` | `Berlin, Germany` |
| `NG_INSTANCE_URL` | `https://neighbourgood.example.com` |
| `NG_ADMIN_NAME` | Name of the person responsible for the instance |
| `NG_ADMIN_CONTACT` | Contact address for other instance admins |

## Email

Without SMTP settings, emails (booking notifications, password resets) are written to the backend log instead of being sent.

| Variable | Default |
|----------|---------|
| `NG_SMTP_HOST` | unset |
| `NG_SMTP_PORT` | `587` |
| `NG_SMTP_TLS` | `true` |
| `NG_SMTP_USER` | unset |
| `NG_SMTP_PASSWORD` | unset |
| `NG_SMTP_FROM` | `noreply@neighbourgood.local` |

## Telegram and AI

Details in [telegram-setup.md](telegram-setup.md).

| Variable | Default | Notes |
|----------|---------|-------|
| `NG_TELEGRAM_BOT_TOKEN` | unset | Bot API token from BotFather; the integration is off while unset |
| `NG_TELEGRAM_BOT_NAME` | unset | Bot username without `@` |
| `NG_TELEGRAM_WEBHOOK_SECRET` | derived | Derived from `NG_SECRET_KEY` and the bot token when unset; the webhook is always protected |
| `NG_AI_PROVIDER` | unset | `ollama` or `openai` (any OpenAI-compatible API). Unset = rule-based matching only |
| `NG_AI_BASE_URL` | `http://localhost:11434` | Ollama default |
| `NG_AI_MODEL` | `llama3.2` | |
| `NG_AI_API_KEY` | unset | Needed for OpenAI, not for Ollama |

## Limits and safety

| Variable | Default | Notes |
|----------|---------|-------|
| `NG_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24 h) | How long a login lasts |
| `NG_MAX_IMAGE_SIZE` | `5242880` (5 MB) | Largest image upload |
| `NG_MAX_REQUEST_BODY_BYTES` | `1048576` (1 MB) | Largest JSON request body (413 above) |
| `NG_UPLOAD_DIR` | `uploads` | Where resource images are stored |
| `NG_MESH_MAX_MESSAGE_AGE_HOURS` | `72` | Mesh messages older than this are refused on sync |
| `NG_WEBHOOK_ALLOW_PRIVATE` | `false` | Allow outbound webhooks to private/LAN addresses (turns the SSRF guard off) |

Built-in limits that are not configurable: 5 login/register attempts per minute per IP, 200 API requests per minute per IP, 10 uploads per minute per IP, and a 15-minute lockout after 5 failed logins for the same email and IP.

## Frontend (behind a reverse proxy)

`ORIGIN`, `ADDRESS_HEADER` and `XFF_DEPTH` are set on the `frontend` service, not in `.env`. See [self-hosting.md](self-hosting.md#running-behind-a-reverse-proxy-nginx--caddy).
