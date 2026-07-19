"""add linked-login identity columns to users

Lets a user sign in with Google (the "YouTube" login) or Twitch in addition to
Discord. Every account stays anchored on Discord (``users.did``); these columns
only hold the linked provider's stable account id (unique, so one provider
account maps to one user) plus a display handle. Web-app-owned, like ``roleid``.

``users`` is already in Alembic's managed set, so this only adds columns and
leaves the bot-owned columns untouched.

Revision ID: 0003_linked_accounts
Revises: 0002_create_queue
Create Date: 2026-07-13
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_linked_accounts"
down_revision: str | None = "0002_create_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_sub", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("google_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("twitch_uid", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("twitch_login", sa.String(255), nullable=True))
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)
    op.create_index("ix_users_twitch_uid", "users", ["twitch_uid"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_twitch_uid", table_name="users")
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_column("users", "twitch_login")
    op.drop_column("users", "twitch_uid")
    op.drop_column("users", "google_name")
    op.drop_column("users", "google_sub")
