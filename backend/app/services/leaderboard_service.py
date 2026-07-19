"""Leaderboard business logic.

Computes the three rolling time windows (today / past 7 days / current month)
in UTC and assembles them, plus the Perfect 30, into one response.
"""

from datetime import datetime, timedelta, timezone

from app.repositories.leaderboard_repository import LeaderboardRepository
from app.schemas.leaderboard import (
    CollectionRanking,
    CountRanking,
    Leaderboard,
    LeaderboardCard,
)
from app.services.mappers import row_to_leaderboard


class LeaderboardService:
    def __init__(self, repo: LeaderboardRepository) -> None:
        self.repo = repo

    def build(self) -> Leaderboard:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = today_start.replace(day=1)

        return Leaderboard(
            today=self._cards(self.repo.top_pulled_since(today_start)),
            past_7_days=self._cards(self.repo.top_pulled_since(week_start)),
            this_month=self._cards(self.repo.top_pulled_since(month_start)),
            perfect_thirty=self._cards(self.repo.perfect_thirty()),
            top_collections=self._rankings(self.repo.top_collections()),
            best_copy_collections=self._rankings(self.repo.top_best_copy()),
            pristine_hunters=self._counts(self.repo.top_pristine()),
        )

    @staticmethod
    def _cards(rows) -> list[LeaderboardCard]:  # noqa: ANN001 - Sequence[Row]
        return [row_to_leaderboard(r) for r in rows]

    @staticmethod
    def _rankings(rows) -> list[CollectionRanking]:  # noqa: ANN001 - Sequence[Row]
        return [
            CollectionRanking(
                user=r._mapping["user"],
                did=str(r._mapping["did"]),
                value=r._mapping["value"],
            )
            for r in rows
        ]

    @staticmethod
    def _counts(rows) -> list[CountRanking]:  # noqa: ANN001 - Sequence[Row]
        return [
            CountRanking(
                user=r._mapping["user"],
                did=str(r._mapping["did"]),
                count=r._mapping["count"],
            )
            for r in rows
        ]
