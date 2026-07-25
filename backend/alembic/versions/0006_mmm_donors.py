"""create mmm_donors (Midweek Monster Mash donor badges)

A web-app-owned table (like ``queue`` / ``link_codes``): the MMM supporter list.
Each row is one donor and their per-tier badge counts; points, totals and ranks
are computed on read by ``mmm_service`` (ported from the original static site).
The Discord-bot-owned tables are left untouched.

Revision ID: 0006_mmm_donors
Revises: 0005_link_codes
Create Date: 2026-07-25
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_mmm_donors"
down_revision: str | None = "0005_link_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIERS = ("initiate", "apprentice", "knight", "master", "ascendant", "luminary", "arbiter")


def upgrade() -> None:
    op.create_table(
        "mmm_donors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(120), nullable=False),
        *[
            sa.Column(tier, sa.Integer(), nullable=False, server_default="0")
            for tier in _TIERS
        ],
    )
    op.create_index("ix_mmm_donors_name", "mmm_donors", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_mmm_donors_name", table_name="mmm_donors")
    op.drop_table("mmm_donors")
