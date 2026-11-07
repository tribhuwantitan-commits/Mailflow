"""Opt-in real PostgreSQL integration; requires MAILFLOW_TEST_POSTGRES_URL."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from test_delivery import PAYLOAD, setup

from alembic import command
from app.config import Settings
from app.main import create_app
from app.models.delivery import APIKey, EmailMessage, OutboxEvent
from app.providers.email import FakeEmailProvider
from app.services.outbox import process_due, process_event


@pytest.fixture
def postgres_database(monkeypatch):
    raw = os.environ.get("MAILFLOW_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("MAILFLOW_TEST_POSTGRES_URL not set; PostgreSQL not validated")
    url = make_url(raw)
    if url.get_backend_name() != "postgresql":
        pytest.fail("MAILFLOW_TEST_POSTGRES_URL must use PostgreSQL")
    schema = f"mailflow_test_{uuid4().hex}"
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_url = url.update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setenv("DATABASE_URL", test_url.render_as_string(hide_password=False))
    cfg = Config("alembic.ini")
    engine = None
    try:
        command.upgrade(cfg, "head")
        engine = create_engine(test_url)
        assert {"outbox_events", "email_messages", "api_keys"}.issubset(
            inspect(engine).get_table_names()
        )
        yield engine, test_url
        engine.dispose()
        engine = None
        command.downgrade(cfg, "0003_delivery")
        command.upgrade(cfg, "head")
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_postgres_phase_flows_and_concurrent_claim(postgres_database):
    engine, url = postgres_database
    settings = Settings(_env_file=None, app_env="test", database_url=SecretStr(str(url)))
    app = create_app(settings, database_engine=engine)
    with TestClient(app) as client:
        org, key = setup(client)
        assert client.get("/v1/auth/me").status_code == 200
        assert client.get(f"/v1/organizations/{org}").status_code == 200
        headers = {"X-API-Key": key["key"], "Idempotency-Key": "pg-one"}
        submitted = client.post("/v1/emails", json=PAYLOAD, headers=headers)
        assert submitted.status_code == 202
        assert (
            client.post("/v1/emails", json=PAYLOAD, headers=headers).json()["id"]
            == submitted.json()["id"]
        )
        email_id = UUID(submitted.json()["id"])
        factory = app.state.session_factory
        with factory() as db:
            assert db.get(APIKey, UUID(key["id"])).is_active
            event_id = db.scalar(select(OutboxEvent.id).where(OutboxEvent.email_id == email_id))
            entered, release = Event(), Event()

            class Blocking(FakeEmailProvider):
                def submit(self, message):
                    entered.set()
                    assert release.wait(10)
                    return super().submit(message)

            provider = Blocking()
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(process_event, factory, provider, event_id)
                assert entered.wait(10)
                second = pool.submit(process_event, factory, provider, event_id)
                assert second.result(timeout=10) is False
                release.set()
                assert first.result(timeout=10)
                assert process_due(factory, provider) == 0
                assert len(provider.submitted_messages) == 1
                with factory() as db:
                    email = db.get(EmailMessage, email_id)
                    assert email.status == "sent" and email.attempt_count == 1
                    assert client.get(f"/v1/emails/{email_id}", headers=headers).status_code == 200
                    assert (
                        client.post(
                            f"/v1/organizations/{org}/api-keys/{key['id']}/revoke"
                        ).status_code
                        == 200
                    )
                    assert client.get("/v1/emails", headers=headers).status_code == 401
