"""Expansion model — maps ``public.expansions``.

This table has no primary key in the legacy schema (``exp``, ``expansion``).
SQLAlchemy requires a mapped PK, so we declare a composite PK over the two
columns. This is an ORM-only convenience for reads; Alembic is configured not
to emit DDL changes against the live database, so no constraint is added.

Legacy query:
    SELECT exp, expansion FROM expansions
        JOIN sets ON expansions.expansion = sets.name ORDER BY sets.rwid
"""

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Expansion(Base):
    __tablename__ = "expansions"

    exp: Mapped[str] = mapped_column(Text, primary_key=True)
    expansion: Mapped[str] = mapped_column(Text, primary_key=True)
