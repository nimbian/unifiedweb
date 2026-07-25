"""MmmDonor model — maps ``public.mmm_donors``.

The Midweek Monster Mash (MMM) donor-badge recognition list. Each row is one
supporter and the **count** of badges they hold in each of the seven tiers; a
tier's point value and title live in the service (:mod:`app.services.mmm_service`),
which computes points / totals / ranks on read (ported from the original static
``app.js``).

Like ``queue`` and ``link_codes`` this is a **web-app-owned** table (created by
Alembic migration ``0006``), not one of the pre-existing Discord-bot tables.
"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# The seven badge tiers, lowest → highest (also the column order below). The
# canonical tier metadata (title, point value) is defined once in mmm_service.
TIER_KEYS = ("initiate", "apprentice", "knight", "master", "ascendant", "luminary", "arbiter")


class MmmDonor(Base):
    __tablename__ = "mmm_donors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Display name (the CSV's identity key); unique so a donor appears once.
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    # Per-tier badge counts (default 0). Column names match TIER_KEYS.
    initiate: Mapped[int] = mapped_column(Integer, default=0)
    apprentice: Mapped[int] = mapped_column(Integer, default=0)
    knight: Mapped[int] = mapped_column(Integer, default=0)
    master: Mapped[int] = mapped_column(Integer, default=0)
    ascendant: Mapped[int] = mapped_column(Integer, default=0)
    luminary: Mapped[int] = mapped_column(Integer, default=0)
    arbiter: Mapped[int] = mapped_column(Integer, default=0)
