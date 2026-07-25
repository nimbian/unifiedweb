"""Alembic migration environment.

Configured for an existing, populated database:
  * The DB URL comes from application settings (single source of truth).
  * ``include_object`` restricts autogenerate to the tables we actually map,
    so Alembic never proposes dropping the Discord-bot-owned tables it does
    not know about.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import settings
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Only these tables are under Alembic's control. Everything else in the schema
# belongs to the Discord bot and must be left strictly alone.
MANAGED_TABLES = {
    "users",
    "mons",
    "collections",
    "sets",
    "cardsinsets",
    "expansions",
    # Created and owned by the web app (unlike the rest, which pre-exist).
    "queue",
    "link_codes",
    "mmm_donors",
}


def include_object(obj, name, type_, reflected, compare_to) -> bool:  # noqa: ANN001
    if type_ == "table":
        return name in MANAGED_TABLES
    # For columns/indexes/constraints, only consider those on managed tables.
    parent_table = getattr(obj, "table", None)
    if parent_table is not None:
        return parent_table.name in MANAGED_TABLES
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
