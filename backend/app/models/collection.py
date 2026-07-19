"""Collection model — maps ``public.collections`` (an owned card instance).

DDL: uid int → users.rwid, monid int → mons.rwid, grade int, holo int (0/1,
**not** boolean), value numeric(10,3), date timestamptz, ed text, rwid PK.
The legacy API reshaped ``holo`` to "Yes"/"No" and ``ed`` to "Unlimited" when
falsy — that presentation logic now lives in the schema/service layer.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.models.base import Base


class Collection(Base):
    __tablename__ = "collections"

    rwid: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[int | None] = mapped_column(
        ForeignKey("users.rwid", ondelete="SET NULL"), index=True
    )
    monid: Mapped[int | None] = mapped_column(
        ForeignKey("mons.rwid", ondelete="SET NULL"), index=True
    )
    grade: Mapped[int | None] = mapped_column(Integer)
    holo: Mapped[int | None] = mapped_column(Integer)
    value: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ed: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="collections", lazy="noload")  # noqa: F821
    mon: Mapped["Mon"] = relationship(lazy="noload")  # noqa: F821
