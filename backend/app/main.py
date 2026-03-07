"""NeighbourGood API – main application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import Base, engine
from app.models import Activity, Booking, Community, CommunityMember, CrisisVote, EmergencyTicket, Invite, KnownInstance, MeshSyncedMessage, Message, RedSkyAlert, Resource, Review, Skill, TelegramLinkToken, User, Webhook  # noqa: F401 – ensure models are registered
from app.routers import activity, auth, bookings, communities, crisis, federation, instance, invites, mesh_sync, messages, resources, reviews, skills, status, users, webhooks
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Community resource-sharing platform with crisis-mode support.",
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)

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
app.include_router(activity.router)
app.include_router(invites.router)
app.include_router(reviews.router)
app.include_router(instance.router)
app.include_router(federation.router)
app.include_router(webhooks.router)
app.include_router(mesh_sync.router)
app.include_router(telegram_router.router)
