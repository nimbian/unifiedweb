"""Data access for the Midweek Monster Mash donor list (``mmm_donors``)."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MmmDonor


class MmmRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_donors(self) -> Sequence[MmmDonor]:
        """Every donor row. Points/totals/ranks are computed in the service (the
        ranking needs the whole set), mirroring the original static site."""
        return self.db.execute(select(MmmDonor)).scalars().all()
