"""DnD-adventure router (read-only views over the DnD bot's database).

  GET /api/dnd/characters         -> all characters (Adventurers table)
  GET /api/dnd/characters/{key}   -> one character's full sheet + equipment
  GET /api/dnd/leaderboard        -> top players by level / gold / abyss / duels
  GET /api/dnd/worldboss          -> current world boss + top damage, recent kills
  GET /api/dnd/achievements       -> achievement catalog with earned counts
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dnd.database import get_dnd_db
from app.dnd.repository import DndRepository
from app.dnd.schemas import (
    AchievementsView,
    CharacterDetail,
    CharacterSummary,
    DndLeaderboard,
    WorldBossView,
)
from app.dnd.service import DndService


def get_dnd_service(db: Annotated[Session, Depends(get_dnd_db)]) -> DndService:
    return DndService(DndRepository(db))


DndServiceDep = Annotated[DndService, Depends(get_dnd_service)]

router = APIRouter(prefix="/dnd", tags=["dnd"])


@router.get("/characters", response_model=list[CharacterSummary], summary="All adventurers")
def list_characters(service: DndServiceDep) -> list[CharacterSummary]:
    return service.list_characters()


@router.get("/characters/{key}", response_model=CharacterDetail, summary="A character sheet")
def get_character(key: int, service: DndServiceDep) -> CharacterDetail:
    return service.character_detail(key)


@router.get("/leaderboard", response_model=DndLeaderboard, summary="DnD leaderboards")
def leaderboard(service: DndServiceDep) -> DndLeaderboard:
    return service.leaderboard()


@router.get("/worldboss", response_model=WorldBossView, summary="World boss status")
def world_boss(service: DndServiceDep) -> WorldBossView:
    return service.world_boss()


@router.get("/achievements", response_model=AchievementsView, summary="Achievement catalog")
def achievements(service: DndServiceDep) -> AchievementsView:
    return service.achievements()
