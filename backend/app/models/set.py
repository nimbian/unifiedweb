"""Set + CardInSet models — map ``public.sets`` and ``public.cardsinsets``.

``sets`` has ``(name, role, rwid)``. Note the legacy quirks:
  * The UNIQUE constraint ``unname`` is on **role**, not name.
  * ``cardsinsets.setid`` FKs to ``sets.rwid``; ``completedsets.setname``
    (bot table) FKs to ``sets.role``.
  * ``rwid`` numeric ranges encode the set kind:
        rwid <= 0           → base sets
        0 < rwid < 50       → creature/monster sets
        50 <= rwid < 99     → item sets
        300 <= rwid < 400   → location sets
    These ranges are encoded as constants in ``set_repository`` rather than
    being scattered through query strings.
"""

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Set(Base):
    __tablename__ = "sets"

    rwid: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text, unique=True)

    cards: Mapped[list["CardInSet"]] = relationship(  # noqa: F821
        back_populates="set",
        lazy="noload",
    )


class CardInSet(Base):
    __tablename__ = "cardsinsets"

    rwid: Mapped[int] = mapped_column(Integer, primary_key=True)
    setid: Mapped[int | None] = mapped_column(
        ForeignKey("sets.rwid", ondelete="CASCADE"), index=True
    )
    monid: Mapped[int | None] = mapped_column(
        ForeignKey("mons.rwid", ondelete="CASCADE"), index=True
    )

    set: Mapped["Set"] = relationship(back_populates="cards", lazy="noload")
    mon: Mapped["Mon"] = relationship(back_populates="cards_in_sets", lazy="noload")  # noqa: F821
