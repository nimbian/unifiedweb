"""Schemas for the buy-from-shop feature (ports the Discord bot's shop buy/haggle).

The "shop" is the system user's collection (uid 0) — cards sold back to it. A
signed-in user can buy them back: a straight buy costs 150% of value, or a
haggle gamble pays 130%–170% on a d20 roll.
"""

from decimal import Decimal

from pydantic import BaseModel, Field


class BuyRequest(BaseModel):
    """Shop cards the authenticated user wants to buy (by collection rwid)."""

    collection_ids: list[int] = Field(..., min_length=1, description="shop collections.rwid values to buy")
    haggle: bool = Field(
        default=False,
        description="Gamble on a d20 persuasion check (130%-170%) instead of the flat 150%.",
    )


class BoughtCard(BaseModel):
    collection_id: int
    name: str | None
    value: Decimal | None
    cost: Decimal  # value * buy rate, rounded to 3 dp


class BuyResult(BaseModel):
    """Outcome of a purchase (mirrors the bot's confirmation message)."""

    bought: list[BoughtCard]
    total_cost: Decimal
    new_gp: Decimal
    rate: float          # the effective rate applied (1.5 straight, or the haggled rate)
    roll: int | None = None  # the d20 roll on a haggle buy; None for a straight buy
