"""Leaderboard schemas.

The leaderboard highlights the single highest-value card(s) *pulled* (acquired,
by ``collections.date``) in three rolling windows — today, the past 7 days, and
the current month — plus the "Perfect 30": every card whose value is exactly
10000. Each window returns all cards tied at that window's maximum value.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class LeaderboardCard(BaseModel):
    """One card on the leaderboard (one owned card == one row)."""

    user: str | None
    collection_id: int
    cr: str | None
    name: str | None
    exp: str | None
    grade: int | None
    holo: bool
    edition: str
    value: Decimal | None
    date: datetime | None


class CollectionRanking(BaseModel):
    """One user's standing in a whole-collection ranking.

    ``did`` is serialized as a string (Discord snowflakes exceed JS safe ints),
    matching the rest of the API, so the frontend can link to the user.
    """

    user: str | None
    did: str
    value: Decimal


class CountRanking(BaseModel):
    """One user's standing in a card-count ranking (``did`` serialized as str)."""

    user: str | None
    did: str
    count: int


class Leaderboard(BaseModel):
    today: list[LeaderboardCard]
    past_7_days: list[LeaderboardCard]
    this_month: list[LeaderboardCard]
    perfect_thirty: list[LeaderboardCard]
    # Whole-collection standings (top 3 each).
    top_collections: list[CollectionRanking]          # by total collection value
    best_copy_collections: list[CollectionRanking]    # by value of one of each (best copy)
    pristine_hunters: list[CountRanking]              # by count of pristine (grade 10 + holo) cards
