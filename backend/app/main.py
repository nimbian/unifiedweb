"""FastAPI application entrypoint.

Replaces the Flask ``app = Flask(__name__)`` monolith. Wires CORS (locked to the
configured frontend origin), logging, the aggregate API router, OpenAPI metadata,
and a health check.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    configure_logging()
    logger.info("Starting %s (%s)", settings.app_name, settings.environment)
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Satchemon card-collection API (migrated from Flask).",
    lifespan=lifespan,
    openapi_url=f"{settings.api_prefix}/openapi.json",
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,  # required for the httpOnly refresh cookie
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)

# Card layer images (Color/Cards/Holo/Grade PNGs) as static files. Mounted under
# the API prefix so the existing reverse-proxy (which forwards /api) serves them.
if os.path.isdir(settings.cards_dir):
    app.mount(
        f"{settings.api_prefix}/cards",
        StaticFiles(directory=settings.cards_dir),
        name="cards",
    )
else:
    logger.warning("cards_dir %r not found; %s/cards not mounted", settings.cards_dir, settings.api_prefix)


@app.get(f"{settings.api_prefix}/health", tags=["health"], summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok"}
