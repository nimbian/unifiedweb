"""create link_codes (bot /link -> /account redemption)

A web-app-owned table (like ``queue``): a one-time short code the Discord bot
generates via ``/link`` and the portal redeems on ``/account`` to attach the
code's ``did`` to the signed-in ``rwid`` without an OAuth roundtrip (PLAN §6).

Creating a brand-new web-owned table — the Discord-bot-owned tables are left
strictly alone (the bot only ever INSERTs into this new table).

Revision ID: 0005_link_codes
Revises: 0004_account_provenance
Create Date: 2026-07-19
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_link_codes"
down_revision: str | None = "0004_account_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "link_codes",
        sa.Column("code", sa.String(16), primary_key=True),
        sa.Column("did", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_link_codes_did", "link_codes", ["did"])


def downgrade() -> None:
    op.drop_index("ix_link_codes_did", table_name="link_codes")
    op.drop_table("link_codes")
