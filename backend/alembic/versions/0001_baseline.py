"""baseline — existing schema, no-op

This revision intentionally does nothing. The Satchemon database already exists
and is populated. Run ``alembic stamp 0001_baseline`` against production to mark
the current schema as the baseline WITHOUT issuing any DDL. Future model changes
are then generated as new revisions on top of this one.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-19
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No-op: the schema already exists in the live database.
    pass


def downgrade() -> None:
    # No-op: never drop the legacy schema.
    pass
