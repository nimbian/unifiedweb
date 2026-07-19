"""Sets router (tab sidebar + per-set ownership drill-down).

  GET /api/sets/sidebar              -> tab buttons (creature/item/location/expansion)
  GET /api/users/{did}/sets/{slug}   -> per-slot ownership for a base/named set
                                        (was the set branch of /api/set/<s>/<did>)
"""

from fastapi import APIRouter

from app.api.dependencies.services import SetServiceDep
from app.schemas.set import SetCardEntry, SetSidebar

router = APIRouter(tags=["sets"])


@router.get("/sets/sidebar", response_model=SetSidebar, summary="Set/expansion tab lists")
def sidebar(service: SetServiceDep) -> SetSidebar:
    return service.sidebar()


@router.get(
    "/users/{did}/sets/{slug}",
    response_model=list[SetCardEntry],
    summary="Per-slot ownership for a base or named set",
)
def set_view(did: int, slug: str, service: SetServiceDep) -> list[SetCardEntry]:
    """``slug`` is ``BaseSets`` or a legacy-encoded set/expansion name."""
    return service.set_view(did, slug)
