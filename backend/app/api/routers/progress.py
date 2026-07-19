"""Progress router — a user's headline stats + per-set completion.

  GET /api/users/{did}/progress  -> general stats + every set's owned/total
"""

from fastapi import APIRouter

from app.api.dependencies.services import ProgressServiceDep
from app.schemas.progress import UserProgress

router = APIRouter(tags=["progress"])


@router.get(
    "/users/{did}/progress",
    response_model=UserProgress,
    summary="Collection progress for a user",
)
def get_progress(did: int, service: ProgressServiceDep) -> UserProgress:
    return service.build(did)
