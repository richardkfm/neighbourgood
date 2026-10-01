"""NeighbourGood API – main application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, literal, text
from sqlalchemy.exc import DataError
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import Base, engine

logger = logging.getLogger(__name__)
from app.middleware.body_limit import BodySizeLimitMiddleware
from app.middleware.csrf import CsrfMiddleware
from app.middleware.nul_bytes import NulByteMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.models import Activity, Booking, Community, CommunityMember, CrisisVote, EmergencyTicket, Event, EventAttendee, FederatedResource, FederatedSkill, InstanceSyncLog, Invite, KnownInstance, MeshCheckin, MeshDeviceKey, MeshSyncedMessage, PasswordResetToken, Message, RedSkyAlert, Resource, SentAlert, Review, Skill, TelegramLinkToken, User, Webhook  # noqa: F401 – ensure models are registered
from app.routers import activity, auth, bookings, communities, crisis, events, federation, federation_sync, instance, invites, matching, mesh_sync, messages, resources, reviews, skills, status, users, webhooks
from app.routers import telegram as telegram_router


# ── Security headers middleware ────────────────────────────────────


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security-related HTTP response headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
        response.headers["X-XSS-Protection"] = "0"
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains"
            )
            response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response


# ── Application setup ──────────────────────────────────────────────


def _column_default_sql(col, dialect) -> str:
    """Render a column's default for ALTER TABLE ... ADD COLUMN, or "" if it has none we can express."""
    if col.server_default is not None:
        arg = col.server_default.arg
        if isinstance(arg, str):
            value = literal(arg).compile(dialect=dialect, compile_kwargs={"literal_binds": True})
        elif hasattr(arg, "text"):
            value = arg.text
        else:
            value = arg.compile(dialect=dialect)
        return f" DEFAULT {value}"
    default = col.default
    if default is not None and default.is_scalar and default.arg is not None:
        # Let the dialect render the literal (e.g. booleans as TRUE/FALSE on PostgreSQL, 1/0 on SQLite)
        value = literal(default.arg, col.type).compile(
            dialect=dialect, compile_kwargs={"literal_binds": True}
        )
        return f" DEFAULT {value}"
    return ""


def _add_missing_columns(bind=None) -> list[str]:
    """Inspect every ORM table and ADD the columns the database is missing.

    Runs on every start so that self-hosted instances upgraded with
    ``docker compose up --build`` get new columns without a manual
    ``alembic upgrade head`` (a missing column makes every query on that
    table fail). Only additive: never drops, renames or alters columns.
    Each column is added in its own transaction, so one failure does not
    block the others. Returns the ``table.column`` names that were added.
    """
    bind = bind or engine
    inspector = inspect(bind)
    added: list[str] = []
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table_name)}
        for col in table.columns:
            if col.name in existing:
                continue
            col_type = col.type.compile(bind.dialect)
            base_sql = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}"
            default_sql = _column_default_sql(col, bind.dialect)
            # SQLite refuses non-constant defaults (e.g. CURRENT_TIMESTAMP) in ADD COLUMN,
            # so fall back to adding the column without one rather than not at all.
            attempts = [base_sql + default_sql, base_sql] if default_sql else [base_sql]
            for sql in attempts:
                try:
                    with bind.begin() as conn:
                        conn.execute(text(sql))
                    break
                except Exception:
                    if sql is attempts[-1]:
                        logger.exception("Could not add missing column %s.%s", table_name, col.name)
            else:
                continue
            added.append(f"{table_name}.{col.name}")
            logger.warning("Added missing column %s.%s to the database schema", table_name, col.name)
    return added


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Community resource-sharing platform with crisis-mode support.",
    lifespan=lifespan,
)

@app.exception_handler(OverflowError)
@app.exception_handler(DataError)
async def out_of_range_handler(request: Request, exc: Exception) -> JSONResponse:
    """Integers beyond the database range (e.g. /resources/99999999999999999999) are a client error, not a 500."""
    return JSONResponse(status_code=422, content={"detail": "Value out of range"})


# Innermost, so its receive() wrapper feeds the endpoint directly: an oversized
# streamed body then surfaces as 413 instead of a generic body-parsing error
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CsrfMiddleware)
app.add_middleware(NulByteMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(status.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(resources.router)
app.include_router(bookings.router)
app.include_router(messages.router)
app.include_router(communities.router)
app.include_router(crisis.router)
app.include_router(skills.router)
app.include_router(events.router)
app.include_router(activity.router)
app.include_router(invites.router)
app.include_router(reviews.router)
app.include_router(instance.router)
app.include_router(federation.router)
app.include_router(federation_sync.router)
app.include_router(webhooks.router)
app.include_router(mesh_sync.router)
app.include_router(matching.router)
app.include_router(telegram_router.router)
