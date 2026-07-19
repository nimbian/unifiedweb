"""Schemas for the sell-cards feature (ports the Discord bot's /sell command)."""

from decimal import Decimal

from pydantic import BaseModel, Field


class SellRequest(BaseModel):
    """Cards the authenticated user wants to sell (by collection rwid)."""

    collection_ids: list[int] = Field(..., min_length=1, description="collections.rwid values to sell")
    haggle: bool = Field(
        default=False,
        description="Gamble on a d20 persuasion check (50%-90%) instead of the flat 70%.",
    )


class SoldCard(BaseModel):
    collection_id: int
    name: str | None
    value: Decimal | None
    payout: Decimal  # value * sell rate, rounded to 3 dp


class SellResult(BaseModel):
    """Outcome of a sale (mirrors the bot's confirmation message)."""

    sold: list[SoldCard]
    total_payout: Decimal
    new_gp: Decimal
    rate: float          # the effective rate applied (0.7 straight, or the haggled rate)
    roll: int | None = None  # the d20 roll on a haggle sale; None for a straight sale
