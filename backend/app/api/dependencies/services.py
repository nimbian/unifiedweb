"""Dependency-injection providers.

FastAPI's ``Depends`` is the composition root: each provider builds a repository
from the request-scoped DB session, then a service from the repository. This is
the explicit DI the migration brief asks for, with no global singletons (except
the stateless ``DriveService``).
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.collection_repository import CollectionRepository
from app.repositories.leaderboard_repository import LeaderboardRepository
from app.repositories.set_repository import SetRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.collection_service import CollectionService
from app.services.drive_service import DriveService
from app.services.leaderboard_service import LeaderboardService
from app.services.progress_service import ProgressService
from app.services.set_service import SetService
from app.services.user_service import UserService

DbSession = Annotated[Session, Depends(get_db)]


# ── Repositories ─────────────────────────────────────────────────────────────
def get_user_repo(db: DbSession) -> UserRepository:
    return UserRepository(db)


def get_collection_repo(db: DbSession) -> CollectionRepository:
    return CollectionRepository(db)


def get_set_repo(db: DbSession) -> SetRepository:
    return SetRepository(db)


def get_leaderboard_repo(db: DbSession) -> LeaderboardRepository:
    return LeaderboardRepository(db)


# ── Services ─────────────────────────────────────────────────────────────────
def get_user_service(
    repo: Annotated[UserRepository, Depends(get_user_repo)],
    set_repo: Annotated[SetRepository, Depends(get_set_repo)],
) -> UserService:
    return UserService(repo, set_repo)


def get_collection_service(
    repo: Annotated[CollectionRepository, Depends(get_collection_repo)],
) -> CollectionService:
    return CollectionService(repo)


def get_set_service(
    set_repo: Annotated[SetRepository, Depends(get_set_repo)],
    collection_repo: Annotated[CollectionRepository, Depends(get_collection_repo)],
) -> SetService:
    return SetService(set_repo, collection_repo)


def get_progress_service(
    set_repo: Annotated[SetRepository, Depends(get_set_repo)],
    collection_repo: Annotated[CollectionRepository, Depends(get_collection_repo)],
) -> ProgressService:
    return ProgressService(set_repo, collection_repo)


def get_auth_service(
    repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> AuthService:
    return AuthService(repo)


def get_leaderboard_service(
    repo: Annotated[LeaderboardRepository, Depends(get_leaderboard_repo)],
) -> LeaderboardService:
    return LeaderboardService(repo)


def get_drive_service() -> DriveService:
    return DriveService()


# Convenience aliases for routers.
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
CollectionServiceDep = Annotated[CollectionService, Depends(get_collection_service)]
SetServiceDep = Annotated[SetService, Depends(get_set_service)]
LeaderboardServiceDep = Annotated[LeaderboardService, Depends(get_leaderboard_service)]
ProgressServiceDep = Annotated[ProgressService, Depends(get_progress_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
DriveServiceDep = Annotated[DriveService, Depends(get_drive_service)]
