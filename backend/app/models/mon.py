"""Mon (card definition) model — maps ``public.mons``.

A "mon" is a card archetype. ``class`` partitions cards into
``Monsters`` / ``Item`` / ``Locations`` (note the legacy class filters are
exactly those strings, including the singular ``Item``). ``name`` embeds a
``(#<cr-code>)`` suffix that the legacy ``getCardsForUser`` matches with
``LIKE '%(#<code>)%'`` — preserved verbatim, not normalized.
"""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Mon(Base):
    __tablename__ = "mons"

    rwid: Mapped[int] = mapped_column(Integer, primary_key=True)
    cr: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    exp: Mapped[str | None] = mapped_column(Text)
    class_: Mapped[str | None] = mapped_column("class", String(15))

    cards_in_sets: Mapped[list["CardInSet"]] = relationship(  # noqa: F821
        back_populates="mon",
        lazy="noload",
    )
