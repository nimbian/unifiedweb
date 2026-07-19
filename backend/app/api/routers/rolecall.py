"""Rolecall / check-in endpoints.

Records a check-in into the pre-existing, Discord-bot-owned ``checkin`` table
(name, id, platform, date). Authenticated by a shared API key passed as a query
param (``apikey``) — distinct from the app's JWT auth. Because ``checkin`` is a
bot-owned table, it is written via raw SQL and left outside Alembic's managed
set (same policy as the trade tables in the sell flow).

Mounted under the API prefix, so the routes are ``GET/POST {api_prefix}/rolecall``
(e.g. ``/api/rolecall``).
"""

from datetime import datetime
from urllib.parse import parse_qs

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import text

from app.api.dependencies.services import DbSession
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["rolecall"])


def _require_api_key(apikey: str | None, authorization: str | None = None) -> None:
    candidate = apikey
    if not candidate and authorization:
        if authorization.lower().startswith("bearer "):
            candidate = authorization.split(None, 1)[1]
        else:
            candidate = authorization

    if not settings.rolecall_api_key or candidate != settings.rolecall_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid API Key")


def _record_checkin(db: DbSession, name: str, user_id: str, platform: str | None) -> None:
    db.execute(
        text(
            "INSERT INTO checkin (name, id, platform, date) "
            "VALUES (:name, :id, :platform, :date)"
        ),
        {"name": name, "id": user_id, "platform": platform, "date": datetime.now()},
    )
    logger.info("rolecall check-in name=%s id=%s platform=%s", name, user_id, platform)


@router.get("/rolecall", summary="Record a check-in (query params)")
@router.get("/stream/rolecall", summary="Legacy rolecall path for older clients")
def rolecall_get(
    user: str,
    userid: str,
    db: DbSession,
    apikey: str | None = None,
    platform: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, str]:
    _require_api_key(apikey, authorization)
    _record_checkin(db, user, userid, platform)
    return {"message": f"User checkin {user}"}


@router.post("/rolecall", summary="Record a check-in (form body or query params)")
@router.post("/stream/rolecall", summary="Legacy rolecall path for older clients")
async def rolecall_post(
    user: str,
    userid: str,
    request: Request,
    db: DbSession,
    apikey: str | None = None,
    platform: str | None = None,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, str]:
    _require_api_key(apikey, authorization)
    # A form-urlencoded body may carry the real userId (falls back to the query param).
    decoded = (await request.body()).decode("utf-8")
    data = parse_qs(decoded)
    user_id = data.get("userId", [userid])[0]
    _record_checkin(db, user, user_id, platform)
    return {"message": f"User checkin {user_id}"}
