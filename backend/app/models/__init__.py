"""ORM models for the Satchemon web application.

The seven tables the web app *reads* (users, mons, collections, sets,
cardsinsets, expansions) are pre-existing and Discord-bot-owned; the remaining
~23 tables in the database (lotto, jackpot, trades, shop, promos, events, …)
are likewise the bot's and are intentionally left unmapped and untouched.

``queue`` is the exception: it is created and owned by the web app (the first
table under Alembic's control) to record sold cards for later processing.
"""

from app.models.base import Base
from app.models.collection import Collection
from app.models.completed_set import CompletedSet
from app.models.expansion import Expansion
from app.models.link_code import LinkCode
from app.models.mmm_donor import MmmDonor
from app.models.mon import Mon
from app.models.queue import Queue
from app.models.set import CardInSet, Set
from app.models.user import User

__all__ = [
    "Base",
    "Collection",
    "CompletedSet",
    "Expansion",
    "LinkCode",
    "MmmDonor",
    "Mon",
    "Queue",
    "CardInSet",
    "Set",
    "User",
]
