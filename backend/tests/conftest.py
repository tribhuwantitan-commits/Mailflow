"""Shared fixtures for backend tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register all model metadata for test schema setup
from app.config import Settings
from app.db.base import Base
from app.main import create_app


@pytest.fixture
def database_engine() -> Iterator[Engine]:
    """Use a shared in-memory SQLite DB for fast isolated API tests."""
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
    )


@pytest.fixture
def app(database_engine: Engine, test_settings: Settings):
    return create_app(test_settings, database_engine=database_engine)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
