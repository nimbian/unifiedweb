"""Aggregate API router — mounts all feature routers under the API prefix."""

from fastapi import APIRouter

from app.api.routers import (
    auth,
    cards,
    collections,
    drive,
    leaderboard,
    progress,
    rolecall,
    sets,
    users,
)
from app.dnd.router import router as dnd_router

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(collections.router)
api_router.include_router(sets.router)
api_router.include_router(leaderboard.router)
api_router.include_router(cards.router)
api_router.include_router(rolecall.router)
api_router.include_router(progress.router)
api_router.include_router(dnd_router)
api_router.include_router(drive.router)
