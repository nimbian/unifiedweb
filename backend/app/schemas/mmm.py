"""Schemas for the Midweek Monster Mash donor badges."""

from pydantic import BaseModel, Field


class BadgeTier(BaseModel):
    """One badge tier in the catalog (the front end maps ``key`` to its art)."""

    key: str = Field(..., description="Stable tier id, e.g. 'initiate'.")
    title: str = Field(..., description="Display title, e.g. 'Initiate of the Guild'.")
    points: float = Field(..., description="Points awarded per badge of this tier.")


class DonorSummary(BaseModel):
    """A supporter's computed standing (points/totals/rank are derived on read)."""

    name: str
    points: float = Field(..., description="Total points = sum(count * tier points).")
    total_badges: int
    rank: int = Field(..., description="Competition rank; donors tied on points share a rank.")
    badges: dict[str, int] = Field(..., description="Per-tier badge counts keyed by tier id.")


class DonorImportResult(BaseModel):
    """Outcome of an admin CSV import."""

    inserted: int
    updated: int
    total: int
