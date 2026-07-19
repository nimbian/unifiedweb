"""Leaderboard router.

  GET /api/leaderboard -> top-value pulls (today / 7 days / month) + Perfect 30
"""

from fastapi import APIRouter

from app.api.dependencies.services import LeaderboardServiceDep
from app.schemas.leaderboard import Leaderboard

router = APIRouter(tags=["leaderboard"])


@router.get("/leaderboard", response_model=Leaderboard, summary="Leaderboard + Perfect 30")
def get_leaderboard(service: LeaderboardServiceDep) -> Leaderboard:
    return service.build()
