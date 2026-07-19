"""Card / collection schemas.

These replace the positional-tuple JSON the Flask ``api.py`` produced. The
legacy frontend (jQuery DataTables) indexed columns by position; the React
frontend consumes named fields instead. Presentation transforms the old API
did inline are documented per field.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class CardRow(BaseModel):
    """A single owned card, as shown in a user's collection grid.

    Legacy tuple order (getFullCollection):
        rwid, cr, name, exp, grade, holo, ed, value, date, mon_rwid, set_name
    Legacy presentation: holo -> "Yes"/"No"; ed -> "Unlimited" when empty.
    """

    collection_id: int          # collections.rwid
    cr: str | None              # mons.cr (challenge rating, custom sort)
    name: str | None            # mons.name (embeds the (#code) suffix)
    exp: str | None             # mons.exp (expansion)
    grade: int | None
    holo: bool                  # derived from holo integer (0/1)
    edition: str                # ed text, or "Unlimited" when empty
    value: Decimal | None
    set_name: str | None        # joined set name (cardsinsets/sets, rwid > 0)
    date: datetime | None = None
    mon_id: int | None = None   # mons.rwid


class SearchRow(BaseModel):
    """A row of the global search grid (was ``getAllCollections`` / /api/getAll)."""

    user: str | None
    collection_id: int
    cr: str | None
    name: str | None
    exp: str | None
    grade: int | None
    holo: bool
    edition: str
    value: Decimal | None
    set_name: str | None
    # The owner's most recent card date; drives the Active pill (active if < 1 month).
    last_active: datetime | None = None


class CardLayers(BaseModel):
    """Filenames available in each card-image layer directory (for compositing)."""

    color: list[str]
    cards: list[str]
    holo: list[str]
    grade: list[str]


class SearchFacets(BaseModel):
    """Distinct values offered by the search column filters (the "selections")."""

    expansions: list[str]
    grades: list[int]
    crs: list[str]


class SearchResults(BaseModel):
    """A page of global-search rows plus the total match count.

    Returned by ``GET /api/search`` so the frontend can load results
    incrementally (infinite scroll): ``offset + limit < total`` means there is a
    next page to fetch.
    """

    items: list[SearchRow]
    total: int
    limit: int
    offset: int
