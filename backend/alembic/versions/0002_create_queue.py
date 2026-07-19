"""create queue table for sold cards

The first real DDL the web app emits. Creates ``public.queue``, a work queue of
cards a user has sold (written inside the sell transaction, drained later). All
pre-existing tables remain untouched — ``env.py``'s ``include_object`` keeps
Alembic scoped to the managed set, which now includes ``queue``.

Apply with ``alembic upgrade head`` (the baseline must already be stamped).

Revision ID: 0002_create_queue
Revises: 0001_baseline
Create Date: 2026-06-19
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_create_queue"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "queue",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("did", sa.BigInteger(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Numeric(10, 3), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_queue_did", "queue", ["did"])


def downgrade() -> None:
    op.drop_index("ix_queue_did", table_name="queue")
    op.drop_table("queue")
