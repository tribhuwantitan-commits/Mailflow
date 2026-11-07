"""SQLAlchemy engine helpers for the PostgreSQL-backed application."""

from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.db import ownership as _ownership  # noqa: F401 - register ORM owner guards


def create_database_engine(
    database_url: str | SecretStr,
    connect_timeout_seconds: int = 5,
) -> Engine:
    """Create a synchronous SQLAlchemy engine without connecting eagerly."""
    url_value = (
        database_url.get_secret_value() if isinstance(database_url, SecretStr) else database_url
    )
    url = make_url(url_value)
    engine_options: dict[str, object] = {"pool_pre_ping": True}

    if url.get_backend_name() == "postgresql":
        engine_options["connect_args"] = {"connect_timeout": connect_timeout_seconds}

    return create_engine(url, **engine_options)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create sessions that keep loaded objects usable after a committed transaction."""
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)


def check_database(engine: Engine) -> None:
    """Raise a SQLAlchemy error if the database cannot execute a trivial query."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
