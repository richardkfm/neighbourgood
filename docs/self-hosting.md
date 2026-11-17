# Self-hosting NeighbourGood

How to run your own NeighbourGood instance: install, update, put it behind a domain with HTTPS, and keep it healthy. For every setting, see [configuration.md](configuration.md).

- [What you need](#what-you-need)
- [Install with the one-line installer](#install-with-the-one-line-installer)
- [Install with Docker Compose](#install-with-docker-compose)
- [First steps after installing](#first-steps-after-installing)
- [Everyday Docker commands](#everyday-docker-commands)
- [Updating](#updating)
- [Running behind a reverse proxy (nginx / Caddy)](#running-behind-a-reverse-proxy-nginx--caddy)
- [Outbound webhooks and private addresses](#outbound-webhooks-and-private-addresses)
- [Optional: local AI](#optional-local-ai)
- [Backups](#backups)

## What you need

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 1 vCPU | 2 vCPU |
| RAM | 1 GB | 2 GB |
| Disk | 5 GB | 20 GB |
| OS | Linux (any modern distro) | Ubuntu 22.04 LTS or newer |
| Docker | 24+ with the Compose v2 plugin (`docker compose`, no hyphen) | latest |
| Open ports | 80, 443 (or 3800 directly for a test) | + 22 for SSH |

A small VPS (around 5 € a month, e.g. Hetzner or DigitalOcean) is plenty for a neighbourhood, and can host several neighbourhoods side by side. Running NeighbourGood takes about 250 MB of memory plus the database; on one CPU core it serves around 100 page views a second, far more than even a busy neighbourhood needs. PostgreSQL runs inside Docker, so you don't need a separate database server.

Installing and updating build the app on the server, and that step briefly needs about 1 GB of memory on its own. On a 1 GB server, add 1–2 GB of swap first (your provider's docs explain how) so the build isn't stopped halfway.

## Install with the one-line installer

```bash
curl -fsSL https://raw.githubusercontent.com/neighbourgood/neighbourgood/main/install.sh | bash
```

The script downloads NeighbourGood to `~/neighbourgood` (change it with `NG_INSTALL_DIR`), creates `.env` from `.env.example` with a fresh secret key, and starts it:

- **With Docker installed**, it runs the full Docker Compose stack (PostgreSQL, backend, frontend). The web app is at http://localhost:3800.
- **Without Docker**, it falls back to a native install for trying things out: a Python virtualenv with SQLite in debug mode and the frontend dev server on http://localhost:5173. Don't use this for a real community; install Docker and run the script again.

Running the script again on an existing install pulls the latest version.

## Install with Docker Compose

Docker Compose starts three containers: PostgreSQL, the FastAPI backend and the SvelteKit frontend.

```bash
git clone https://github.com/neighbourgood/neighbourgood.git
cd neighbourgood
cp .env.example .env
```

Generate a secret key. The backend refuses to start without one:

```bash
echo "NG_SECRET_KEY=$(openssl rand -hex 32)" >> .env
```

Make your own account a platform admin (use the email you will sign up with):

```bash
echo 'NG_ADMIN_EMAILS=["you@example.com"]' >> .env
```

Build and start everything (the first run takes 2–3 minutes):

```bash
docker compose up --build
```

When the backend logs `Application startup complete`, the stack is ready:

| Service | URL |
|---------|-----|
| Web app | http://localhost:3800 |
| API | http://localhost:8300 |
| Interactive API docs (Swagger) | http://localhost:8300/docs |
| API reference (ReDoc) | http://localhost:8300/redoc |

Before you open it to your neighbours, also fill in the instance identity in `.env` (`NG_INSTANCE_NAME`, `NG_INSTANCE_REGION`, `NG_INSTANCE_URL`, `NG_ADMIN_NAME`, `NG_ADMIN_CONTACT`) and, for emails, the `NG_SMTP_*` settings. See [configuration.md](configuration.md).

## First steps after installing

1. Open the web app and click **Sign Up**. An account whose email is in `NG_ADMIN_EMAILS` becomes a platform admin, which is needed to manage the federation directory and send cross-instance Red Sky alerts.
2. The onboarding wizard lets you search for a community near you, join one, or create one. As the creator you are the community's admin.
3. Create invite links on the community page and share them with your neighbours.
4. Optional: connect the Telegram bot ([telegram-setup.md](telegram-setup.md)).

## Everyday Docker commands

Start in the background:

```bash
docker compose up --build -d
```

Follow the logs:

```bash
docker compose logs -f
```

Stop everything (data stays in the PostgreSQL volume):

```bash
docker compose down
```

Stop and delete **all** data:

```bash
docker compose down -v
```

Rebuild one service after a code change:

```bash
docker compose up --build backend
```

## Updating

```bash
git pull
docker compose up --build -d
```

New database columns are added automatically when the backend starts (the log shows `Added missing column …`), so a normal update needs no extra step. Alembic migrations remain the source of truth for everything else (constraints, indexes, data migrations). To apply them on a running stack:

```bash
docker compose exec backend alembic upgrade head
```

After an update, open browser tabs show a "new version available" banner once; reloading switches to the new version.

## Running behind a reverse proxy (nginx / Caddy)

In production you normally terminate TLS in nginx or Caddy and forward to the `frontend` container (port 3800). **You must tell the frontend which header carries the real client address.** Otherwise the frontend only sees the proxy's IP, forwards that to the backend, and every user shares one IP, so the per-IP rate limits (5 logins/min, 200 requests/min) and the per-(email, IP) login lockout trip for everyone at once.

How the address flows: browser → proxy → `frontend` (`hooks.server.ts` calls `event.getClientAddress()` and sends it to the backend as `X-Forwarded-For`) → `backend` (trusts that header only when the connection comes from a private or loopback address, i.e. your Docker network). Set these on the **`frontend`** service:

| Variable | Value | Meaning |
|----------|-------|---------|
| `ORIGIN` | `https://neighbourgood.example.com` | The public URL people type; required for form posts and redirects |
| `ADDRESS_HEADER` | `X-Forwarded-For` | Read the client IP from this header |
| `XFF_DEPTH` | `1` | Number of trusted proxies in front of the frontend. The client IP is taken that many entries from the **right** of the header, so a client cannot spoof it. Use `2` if a second proxy (e.g. a CDN) sits in front of your nginx/Caddy |

When `ADDRESS_HEADER` is set, the proxy **must always send that header**, otherwise the frontend answers with a 500. Keep the `frontend` port reachable only from the proxy (bind it to `127.0.0.1:3800` or an internal Docker network), and do not publish the backend's port 8300 to the internet.

**nginx**

```nginx
server {
    listen 443 ssl http2;
    server_name neighbourgood.example.com;
    # ssl_certificate / ssl_certificate_key ...

    client_max_body_size 10m;   # image uploads

    location / {
        proxy_pass http://127.0.0.1:3800;
        proxy_set_header Host $host;
        # Appends the connecting client's address to any X-Forwarded-For the
        # client sent, so the rightmost entry (XFF_DEPTH=1) is always genuine.
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Caddy**

```caddy
neighbourgood.example.com {
    # Caddy sets X-Forwarded-For (overwriting anything the client sent) and
    # handles TLS certificates automatically.
    reverse_proxy 127.0.0.1:3800
}
```

**docker-compose.yml** (`frontend` service)

```yaml
    environment:
      ORIGIN: "https://neighbourgood.example.com"
      PORT: "3800"
      API_BACKEND: "http://backend:8300"
      ADDRESS_HEADER: "X-Forwarded-For"
      XFF_DEPTH: "1"
```

Also set `NG_CORS_ORIGINS='["https://neighbourgood.example.com"]'` and `NG_FRONTEND_URL=https://neighbourgood.example.com` for the backend. To check that it works, log in from two different networks and confirm that failed logins on one do not rate-limit the other.

## Outbound webhooks and private addresses

Webhook URLs are rejected when they use a scheme other than `http`/`https` or resolve to a private, loopback, link-local, reserved or multicast address (SSRF protection). The check runs when the webhook is created and again at every delivery. If you need to notify a service on your LAN, set `NG_WEBHOOK_ALLOW_PRIVATE=true`.

## Optional: local AI

Smart matching and the Telegram assistant can use an optional LLM (Ollama or any OpenAI-compatible API). Everything works without one; matching then stays rule-based. To run a model on your own server:

| Resource | Minimum | Notes |
|----------|---------|-------|
| CPU | 4+ cores | Inference is slow on fewer than 4 cores |
| RAM | 8 GB | 16 GB recommended for 7B models |
| Disk | 10 GB extra | Per model (e.g. `llama3.2:3b` ≈ 2 GB, `mistral:7b` ≈ 4 GB) |
| GPU (optional) | CUDA / ROCm / Apple Silicon | Much faster, not required |

For small servers we recommend `llama3.2:3b` via [Ollama](https://ollama.com). Setup is in [telegram-setup.md](telegram-setup.md#7-setting-up-local-ai).

## Backups

There are no automated backups yet (see the [roadmap](roadmap.md)). Back up the database and the `backend-uploads` volume (resource images) yourself, for example with a nightly `pg_dump`:

```bash
docker compose exec -T db pg_dump -U neighbourgood neighbourgood > neighbourgood-$(date +%F).sql
```

Members can download their own data at any time in **Settings** under *Your data* (*Download my data*).
