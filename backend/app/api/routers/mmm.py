"""Midweek Monster Mash donor-badge router (public, read-only).

  GET /api/mmm/badges        -> the badge-tier catalog (title + point value)
  GET /api/mmm/donors        -> the ranked supporter leaderboard
  GET /api/mmm/donors/{name} -> one supporter's standing (404 if not listed)
"""

from fastapi import APIRouter

from app.api.dependencies.services import MmmServiceDep
from app.schemas.mmm import BadgeTier, DonorSummary

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
