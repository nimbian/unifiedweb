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

    # Security / JWT (RS256 asymmetric — PLAN §5 / kickoff decision).
    #
    # The portal SIGNS access/refresh tokens with the RSA *private* key; in Phase 2
    # the arena server will VERIFY with the *public* key only (it never holds the
    # private key). Provide the key material as PEM — either a path to a file
    # (preferred in prod; keep the files out of git) or the PEM contents inline
    # (handy for containers/CI). A path wins over an inline value. Keys are
    # resolved lazily (only when a token is signed/verified), so tools that import
    # settings without minting tokens (e.g. Alembic) don't need them.
    jwt_algorithm: str = "RS256"
    jwt_private_key_path: str = ""
    jwt_public_key_path: str = ""
    jwt_private_key: str = ""   # inline PEM alternative to jwt_private_key_path
    jwt_public_key: str = ""    # inline PEM alternative to jwt_public_key_path
    # HS* fallback secret — only used when jwt_algorithm starts with "HS"
    # (a simple symmetric dev mode). Left empty for the RS256 default.
    jwt_secret: str = ""
    # v1-token grace (PLAN §5 "token compatibility"): the *previous* newweb HS256
    # secret. While set, tokens signed by the old backend still verify, so existing
    # browser sessions survive the 7-day refresh window. The subject shape (v1
    # ``sub = did`` vs v2 ``sub = rwid``) is handled separately in the auth service;
    # this only lets the old signature validate. Remove once the window drains.
    jwt_legacy_secret: str = ""
    jwt_legacy_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # OAuth providers. Users sign in with ANY of the three; login resolves the
    # provider id to a ``users`` row or creates one (PLAN §5), and the token
    # subject is the canonical ``users.rwid``. All three providers redirect the
    # browser to the same SPA callback route. Leave the ``*_redirect_uri`` values
    # blank to derive them from ``frontend_origin`` (``{frontend_origin}/auth/callback``)
    # so the public URL is set in one place; set one explicitly only to override
    # a single provider.
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
