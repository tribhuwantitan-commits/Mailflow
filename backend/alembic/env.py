"""Alembic environment using the same environment-based database settings as the app."""

from logging.config import fileConfig

from sqlalchemy.engine import Engine

import app.models  # noqa: F401 - register model metadata for Alembic
from alembic import context
from app.config import Settings
from app.database import create_database_engine
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = Settings()
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without creating a live database connection."""
    context.configure(
        url=settings.database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using the configured database URL."""
    engine: Engine = create_database_engine(
        settings.database_url,
        settings.database_connect_timeout_seconds,
    )
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
