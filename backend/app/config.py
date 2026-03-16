"""Application configuration using pydantic-settings."""

import logging
import warnings

from pydantic_settings import BaseSettings

_DEFAULT_SECRET = "change-me-in-production-use-a-real-secret"

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    app_name: str = "NeighbourGood"
    app_version: str = "1.9.5.1"
    debug: bool = False
    database_url: str = "sqlite:///./neighbourgood.db"

    # Dual-state: "blue" (normal) or "red" (crisis)
    platform_mode: str = "blue"

    # Auth
    secret_key: str = _DEFAULT_SECRET
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Uploads
    upload_dir: str = "uploads"
    max_image_size: int = 5 * 1024 * 1024  # 5 MB

    # Email / SMTP (optional – logs to console when unconfigured)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_tls: bool = True
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@neighbourgood.local"

    # Frontend URL (used in email notifications)
    frontend_url: str = "http://localhost:3800"

    # CORS
    cors_origins: list[str] = ["http://localhost:3800", "http://localhost:5173"]

    # Instance identity (for federation directory)
    instance_name: str = "My NeighbourGood"
    instance_description: str = ""
    instance_region: str = ""
    instance_url: str = ""
    admin_name: str = ""
    admin_contact: str = ""

    # Telegram bot integration (optional — leave empty to disable)
    telegram_bot_token: str = ""
    telegram_bot_name: str = ""        # Username without @, e.g. "NeighbourGoodBot"
    telegram_webhook_secret: str = ""  # Random string to validate inbound callbacks

    # AI / LLM integration (optional — matching works rule-based when unset)
    ai_provider: str | None = None      # "ollama" or "openai" (any OpenAI-compatible API)
    ai_base_url: str = "http://localhost:11434"  # Ollama default
    ai_model: str = "llama3.2"
    ai_api_key: str | None = None       # Required for OpenAI, optional for Ollama

    model_config = {"env_prefix": "NG_", "env_file": ".env"}


settings = Settings()

# ── Secret key validation ──────────────────────────────────────────
if settings.secret_key == _DEFAULT_SECRET:
    if settings.debug:
        warnings.warn(
            "Using default secret key – set NG_SECRET_KEY in production!",
            stacklevel=1,
        )
    else:
        raise RuntimeError(
            "INSECURE: default secret key detected. "
            "Set the NG_SECRET_KEY environment variable to a random string "
            "(at least 32 characters) before running in production. "
            "Set NG_DEBUG=true to bypass this check during development."
        )

if len(settings.secret_key) < 32 and not settings.debug:
    raise RuntimeError(
        "NG_SECRET_KEY must be at least 32 characters long in production."
    )
