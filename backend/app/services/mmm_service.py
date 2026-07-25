"""Midweek Monster Mash donor-badge business logic.

Ports the computation from the original static ``app.js``: each donor row carries
a per-tier badge count; from those we derive **total badges**, **points**
(``sum(count * tier_points)``) and a **competition rank** (donors tied on points
share a rank, and the next distinct score skips the intervening places — the
"1-2-2-4" scheme). The badge catalog (tier order, titles, point values) is the
authoritative copy that used to live in ``app.js``; the front end maps each
tier ``key`` to its emblem art.
"""

from dataclasses import dataclass

from fastapi import HTTPException, status

from app.models import MmmDonor
from app.repositories.mmm_repository import MmmRepository
from app.schemas.mmm import BadgeTier, DonorSummary


@dataclass(frozen=True)
class _Tier:
    key: str
    title: str
    points: float


# Lowest → highest. Order matters: it is the display order and the tie-break-free
# progression shown in the gallery. Mirrors the BADGES array in the old app.js.
BADGES: tuple[_Tier, ...] = (
    _Tier("initiate", "Initiate of the Guild", 0.5),
    _Tier("apprentice", "Apprentice of the Arcane Order", 5),
    _Tier("knight", "Knight of the Grand Council", 25),
    _Tier("master", "Master of the Realm", 75),
    _Tier("ascendant", "Ascendant of the Platinum Throne", 125),
    _Tier("luminary", "Luminary of the Prismatic Order", 175),
    _Tier("arbiter", "Arbiter of the Cosmic Balance", 275),
)


class MmmService:
    def __init__(self, repo: MmmRepository) -> None:
        self.repo = repo

    @staticmethod
    def badges() -> list[BadgeTier]:
        """The badge-tier catalog (lowest → highest)."""
        return [BadgeTier(key=t.key, title=t.title, points=t.points) for t in BADGES]

    def leaderboard(self) -> list[DonorSummary]:
        """All donors, ranked. Names that are blank are dropped (as in app.js)."""
        return self._rank([r for r in self.repo.list_donors() if (r.name or "").strip()])

    def donor(self, name: str) -> DonorSummary:
        """A single donor by name (case-insensitive). 404 if not listed.

        The whole set is ranked first because a donor's ``rank`` is only meaningful
        relative to everyone else (same as the original profile page).
        """
        target = name.strip().lower()
        for d in self.leaderboard():
            if d.name.lower() == target:
                return d
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"No donor named {name!r} is listed.")

    # ── internals ────────────────────────────────────────────────────────────
    @staticmethod
    def _summarize(row: MmmDonor) -> DonorSummary:
        counts = {t.key: max(0, getattr(row, t.key) or 0) for t in BADGES}
        total = sum(counts.values())
        # Points are multiples of 0.5 (only 'initiate' is fractional), so rounding
        # to one decimal is exact — no float/banker's-rounding surprises.
        points = round(sum(counts[t.key] * t.points for t in BADGES), 1)
        return DonorSummary(name=row.name.strip(), points=points, total_badges=total,
                            rank=0, badges=counts)

    @classmethod
    def _rank(cls, rows: list[MmmDonor]) -> list[DonorSummary]:
        donors = [cls._summarize(r) for r in rows]
        # Order by points desc, then total badges desc, then name (stable, case-insensitive).
        donors.sort(key=lambda d: (-d.points, -d.total_badges, d.name.lower()))
        previous_points: float | None = None
        current_rank = 0
        for index, d in enumerate(donors):
            if d.points != previous_points:
                current_rank = index + 1
            d.rank = current_rank
            previous_points = d.points
        return donors
