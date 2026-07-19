"""Collections router (a user's owned cards + global search).

  GET /api/users/{did}/cards               -> full collection grid
  GET /api/users/{did}/cards?category=...  -> monsters | items | locations
  GET /api/users/{did}/cards/cr/{cr}       -> CR drill-down   (was /api/cs/<c>/<did>)
  GET /api/search                          -> global search   (was /api/getAll)
"""

from typing import Literal

from fastapi import APIRouter, Query

from app.api.dependencies.auth import CurrentUser
from app.api.dependencies.services import CollectionServiceDep
from app.schemas.buy import BuyRequest, BuyResult
from app.schemas.card import CardRow, SearchFacets, SearchResults
from app.schemas.sell import SellRequest, SellResult

router = APIRouter(tags=["collections"])

Category = Literal["full", "monsters", "items", "locations"]


@router.get(
    "/users/{did}/cards",
    response_model=list[CardRow],
    summary="A user's owned cards (optionally filtered by category)",
)
def get_cards(
    did: int,
    service: CollectionServiceDep,
    category: Category = Query(default="full"),
) -> list[CardRow]:
    if category == "full":
        return service.full_collection(did)
    return service.by_category(did, category)


@router.get(
    "/users/{did}/cards/cr/{cr}",
    response_model=list[CardRow],
    summary="A user's owned cards for a challenge rating",
)
def get_cards_by_cr(did: int, cr: str, service: CollectionServiceDep) -> list[CardRow]:
    return service.by_cr(did, cr)


@router.get("/search", response_model=SearchResults, summary="Global collection search (paged)")
def search(
    service: CollectionServiceDep,
    q: str | None = Query(default=None, description="Case-insensitive filter across user/card/expansion/set."),
    holo: bool | None = Query(default=None, description="Filter by holo (true) / non-holo (false)."),
    exp: str | None = Query(default=None, description="Filter by exact expansion."),
    grade: int | None = Query(default=None, description="Filter by exact grade."),
    cr: str | None = Query(default=None, description="Filter by exact challenge rating."),
    name: str | None = Query(default=None, description="Filter by card-name substring (the Card column)."),
    active: bool | None = Query(default=None, description="Filter by owner activity (active = card < 1 month old)."),
    sort: str | None = Query(default=None, description="Column to sort by (e.g. name, user, cr, value)."),
    direction: str = Query(default="asc", pattern="^(asc|desc)$", description="Sort direction."),
    limit: int = Query(default=50, ge=1, le=200, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Rows to skip (for incremental loading)."),
) -> SearchResults:
    return service.search(q, holo, exp, grade, cr, name, active, sort, direction, limit, offset)


@router.get(
    "/search/facets",
    response_model=SearchFacets,
    summary="Distinct expansions and grades for the search filters",
)
def search_facets(service: CollectionServiceDep) -> SearchFacets:
    return service.search_facets()


@router.post(
    "/me/sell",
    response_model=SellResult,
    summary="Sell your own cards (70% of value)",
)
def sell_cards(
    payload: SellRequest,
    user: CurrentUser,
    service: CollectionServiceDep,
) -> SellResult:
    """Sell cards belonging to the authenticated user. The seller is resolved from
    the access token (never from the request body), so a user can only ever sell
    their own cards.
    """
    return service.sell(int(user.did), payload)


@router.post(
    "/me/buy",
    response_model=BuyResult,
    summary="Buy cards from the shop (150% of value, or haggle)",
)
def buy_cards(
    payload: BuyRequest,
    user: CurrentUser,
    service: CollectionServiceDep,
) -> BuyResult:
    """Buy shop cards (the system user's uid-0 collection) for the authenticated
    user. The buyer is resolved from the access token; only cards currently in
    the shop can be bought, and the buyer must have enough GP.
    """
    return service.buy(int(user.did), payload)
