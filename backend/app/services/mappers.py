"""Row -> schema mapping helpers.

Centralizes the presentation transforms the legacy ``api.py`` did inline:
  * ``holo`` integer (0/1) -> boolean
  * empty ``ed`` -> "Unlimited"
so they are defined once and not duplicated across services.
"""

from sqlalchemy import Row

from app.schemas.card import CardRow, SearchRow
from app.schemas.leaderboard import LeaderboardCard


def _edition(ed: str | None) -> str:
    return ed if ed else "Unlimited"


def row_to_card(row: Row) -> CardRow:
    m = row._mapping
    return CardRow(
        collection_id=m["collection_id"],
        cr=m["cr"],
        name=m["name"],
        exp=m["exp"],
        grade=m["grade"],
        holo=bool(m["holo"]),
        edition=_edition(m["ed"]),
        value=m["value"],
        set_name=m["set_name"],
        date=m.get("date"),
        mon_id=m.get("mon_id"),
    )


def row_to_search(row: Row) -> SearchRow:
    m = row._mapping
    return SearchRow(
        user=m["user"],
        collection_id=m["collection_id"],
        cr=m["cr"],
        name=m["name"],
        exp=m["exp"],
        grade=m["grade"],
        holo=bool(m["holo"]),
        edition=_edition(m["ed"]),
        value=m["value"],
        set_name=m["set_name"],
        last_active=m.get("last_active"),
    )


def row_to_leaderboard(row: Row) -> LeaderboardCard:
    m = row._mapping
    return LeaderboardCard(
        user=m["user"],
        collection_id=m["collection_id"],
        cr=m["cr"],
        name=m["name"],
        exp=m["exp"],
        grade=m["grade"],
        holo=bool(m["holo"]),
        edition=_edition(m["ed"]),
        value=m["value"],
        date=m["date"],
    )
