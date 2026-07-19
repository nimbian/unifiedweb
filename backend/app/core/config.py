"""Application configuration.

Replaces the legacy ``config.yml`` + ``yaml.safe_load`` approach with
``pydantic-settings``. Values are read from environment variables (and an
optional ``.env`` file), validated, and exposed as a typed singleton.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Satchemon API"
    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api"

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://pybot:dbpass@127.0.0.1:5432/dbname",
        description="SQLAlchemy URL for the existing PostgreSQL database.",
    )
    db_echo: bool = False

    # The DnD-adventure bot's database (read-only). Empty -> derived from
    # ``database_url`` by swapping the database name to ``dndbot`` (same server,
    # reused credentials). Set explicitly to point elsewhere.
    dndbot_database_url: str = ""

    # Security / JWT
    jwt_secret: str = "change-me-please-32-bytes-minimum"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # OAuth providers. Users authenticate with any linked provider; every account
    # is anchored on Discord (the token subject stays the Discord id). All three
    # providers redirect the browser to the same SPA callback route. Leave the
    # ``*_redirect_uri`` values blank to derive them from ``frontend_origin``
    # (``{frontend_origin}/auth/callback``) so the public URL is set in one place;
    # set one explicitly only to override a single provider.
    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = ""

    # Google (used as the "YouTube" sign-in — OpenID Connect identity).
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    # Twitch OAuth.
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    twitch_redirect_uri: str = ""

    # Frontend / CORS / cookies
    frontend_origin: str = "http://localhost:5173"
    cookie_secure: bool = False
    refresh_cookie_name: str = "satchemon_refresh"

    # Google Drive
    google_service_account_file: str = "gc.json"
    google_drive_folder_id: str = "1GPKCdlyjwEqDpLsJ5XUV1ak1zr52HF_z"

    # Card layer images (Color/Cards/Holo/Grade), served as static files under
    # ``{api_prefix}/cards``.
    cards_dir: str = "cards"

    # Shared API key for the rolecall/check-in endpoints (not the app JWT).
    rolecall_api_key: str = ""

    @model_validator(mode="after")
    def _derive_redirect_uris(self) -> "Settings":
        """Default any blank OAuth redirect URI to ``{frontend_origin}/auth/callback``.

        The SPA serves the ``/auth/callback`` route on its own origin, so all three
        providers share it. Deriving from ``frontend_origin`` keeps the public URL
        in one place (register that exact value in each provider's console).
        """
        callback = f"{self.frontend_origin.rstrip('/')}/auth/callback"
        if not self.discord_redirect_uri:
            self.discord_redirect_uri = callback
        if not self.google_redirect_uri:
            self.google_redirect_uri = callback
        if not self.twitch_redirect_uri:
            self.twitch_redirect_uri = callback
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor used both directly and as a FastAPI dependency."""
    return Settings()


settings = get_settings()
