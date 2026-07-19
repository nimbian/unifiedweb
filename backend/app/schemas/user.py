"""User-facing schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class UserSummary(BaseModel):
    """One row of the "All users" table (was ``getAllUsers`` / users.j2).

    Legacy SQL returned a tuple ``(name, did, count(value), sum(value), gp)``.
    """

    # ``coerce_numbers_to_str`` lets the integer ``users.did`` column populate the
    # string ``did`` field below.
    model_config = ConfigDict(from_attributes=True, coerce_numbers_to_str=True)

    name: str | None
    # Serialized as a string: Discord snowflake ids exceed JS Number.MAX_SAFE_INTEGER
    # (2^53-1), so a JSON *number* would lose precision in the browser and break the
    # /user/{did} links and the card lookups they drive. Matches UserProfile.did,
    # which is already a str.
    did: str
    card_count: int
    collection_value: Decimal
    gp: Decimal
    # Most recent card date; drives the Active pill (active if < 1 month old).
    last_active: datetime | None = None


class UserProfile(BaseModel):
    """Header info for a user's collection page."""

    did: str
    name: str | None
    gp: Decimal
    # The user's chosen role: ``roleid`` is the completed set's rwid (the picker
    # value), ``role`` is the ``sets.role`` text shown below the name. Both null
    # when no role is set.
    roleid: int | None = None
    role: str | None = None


class RoleOption(BaseModel):
    """One selectable role — a set the user has completed."""

    rwid: int
    name: str | None
    role: str | None


class RoleUpdate(BaseModel):
    """Request body to set/clear the caller's role (``None`` clears it)."""

    roleid: int | None = None


class RoleResult(BaseModel):
    """The caller's role after an update."""

    roleid: int | None
    role: str | None
