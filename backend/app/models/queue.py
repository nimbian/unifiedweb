"""Queue model — maps ``public.queue``.

A work queue of cards a user has sold, written inside the sell transaction and
drained by a later out-of-band process. Unlike the other models (which map
pre-existing Discord-bot tables), this table is **created and owned by the web
app** — it is the first table under Alembic's control (see migration
``0002_create_queue``).

Each row records one sold card:
  * ``did``           — the seller's Discord id (``users.did``)
  * ``collection_id`` — the sold card's ``collections.rwid`` (the "card number")
  * ``value``         — the payout the seller received (card value * sell rate)
"""

from decimal import Decimal

from sqlalchemy import BigInteger, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Queue(Base):
    __tablename__ = "queue"

    # Surrogate primary key (the three business fields below are the payload).
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    did: Mapped[int] = mapped_column(BigInteger, index=True)
    collection_id: Mapped[int] = mapped_column(Integer)
    value: Mapped[Decimal] = mapped_column(Numeric(10, 3))
