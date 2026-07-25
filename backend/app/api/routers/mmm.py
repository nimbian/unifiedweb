"""Midweek Monster Mash donor-badge router.

  GET  /api/mmm/badges        -> the badge-tier catalog (title + point value)
  GET  /api/mmm/donors        -> the ranked supporter leaderboard
  GET  /api/mmm/donors/{name} -> one supporter's standing (404 if not listed)
  POST /api/mmm/admin/donors  -> replace donor data from an uploaded CSV (admin)

The reads are public; the import is gated by the ``admin_discord_ids`` allowlist.
"""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.dependencies.auth import CurrentAdmin
from app.api.dependencies.services import MmmServiceDep
from app.schemas.mmm import BadgeTier, DonorImportResult, DonorSummary

router = APIRouter(prefix="/mmm", tags=["mmm"])


@router.get("/badges", response_model=list[BadgeTier], summary="Badge tier catalog")
def badges(service: MmmServiceDep) -> list[BadgeTier]:
    return service.badges()


@router.get("/donors", response_model=list[DonorSummary], summary="Donor leaderboard")
def donors(service: MmmServiceDep) -> list[DonorSummary]:
    return service.leaderboard()


@router.get("/donors/{name}", response_model=DonorSummary, summary="A single donor by name")
def donor(name: str, service: MmmServiceDep) -> DonorSummary:
    return service.donor(name)


@router.post(
    "/admin/donors",
    response_model=DonorImportResult,
    summary="Import/replace donor data from a CSV (admin only)",
)
async def import_donors(
    admin: CurrentAdmin,  # noqa: ARG001 — gate only; presence enforces admin access
    service: MmmServiceDep,
    file: Annotated[UploadFile, File(description="donors.csv (name + per-tier columns)")],
) -> DonorImportResult:
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="The file must be UTF-8 CSV text."
        ) from exc
    try:
        return service.import_csv_text(text)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
