"""add web-account provenance columns to users

Records how a ``users`` row was first created by the portal's resolve-or-create
login (PLAN §5). Both columns are web-app-owned, nullable and additive:

  * ``created_at``  — when the portal INSERTed the row (NULL for pre-existing and
    bot-created rows; the app sets it, so there is no server default and no
    table rewrite / misleading backfill on the existing populated table).
  * ``created_via`` — which provider first minted the account
    ('discord' | 'google' | 'twitch').

Like ``0003_linked_accounts`` this only adds columns to the already-managed
``users`` table; the Discord-bot-owned tables are left strictly alone.

Revision ID: 0004_account_provenance
Revises: 0003_linked_accounts
Create Date: 2026-07-19
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_account_provenance"
down_revision: str | None = "0003_linked_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("created_via", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "created_via")
    op.drop_column("users", "created_at")
