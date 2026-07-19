"""Progress page schemas — headline collection stats + per-set completion."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class ProgressStats(BaseModel):
    """The general-stats block at the top of a user's progress page."""

    total_value: Decimal          # sum of every owned card's value
    top_value: Decimal            # sum of one of each (the most valuable copy per mon)
    total_cards: int              # number of owned card instances
    unique_cards: int             # number of distinct mons owned


class SetProgress(BaseModel):
    """One set block: how many of the set's cards the user owns, out of the total.

    ``category`` maps to the collection page's tab (``baseSets`` / ``sets`` /
    ``expansions``) and ``slug`` to that tab's picker value, so the frontend can
    deep-link straight to the set. ``group`` is the sub-section within the Unique
    Sets tab (``Creatures`` / ``Items`` / ``Locations``); it is ``None`` for base
    sets and expansions.
    """

    name: str
    slug: str
    category: Literal["baseSets", "sets", "expansions"]
    group: str | None = None
    # The set's role (``sets.role``); shown when the set is complete. None for base
    # sets (which are per-class views, not single set rows) and roleless sets.
    role: str | None = None
    owned: int
    total: int


class UserProgress(BaseModel):
    stats: ProgressStats
    sets: list[SetProgress]
