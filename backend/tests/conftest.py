"""Shared fixtures for backend tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register all model metadata for test schema setup
from app.config import Settings
from app.db.base import Base
from app.main import create_app
from app.models.quota import DEFAULT_PLANS, SendingPlan


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
    # create_all builds tables but does not run the seed migration, so the plan
    # catalogue has to be inserted here for quota checks to resolve a plan.
    with Session(engine) as session:
        session.add_all([SendingPlan(**plan) for plan in DEFAULT_PLANS])
        session.commit()
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


def enable_sending(client, organization_id: str, domain: str | None = None) -> dict:
    """Give a tenant a verified sending domain.

    Registration goes through ``/v1/organizations/{id}/domains`` so tests exercise
    the real ownership check; with MAIL_PROVIDER=fake the no-op verifier marks it
    verified immediately. A domain belongs to exactly one tenant, so when two
    organizations need to exist the second one gets its own.
    """
    target = domain or f"tenant-{organization_id[:8]}.example.com"
    response = client.post(f"/v1/organizations/{organization_id}/domains", json={"domain": target})
    if response.status_code == 409 and domain:
        response = client.post(
            f"/v1/organizations/{organization_id}/domains",
            json={"domain": f"tenant-{organization_id[:8]}.example.com"},
        )
    assert response.status_code == 201, response.text
    return response.json()
