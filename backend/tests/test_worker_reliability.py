"""Worker fencing, concurrent claims, recovery and visibility tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from test_delivery import PAYLOAD, setup

from app.database import create_session_factory
from app.db.base import Base
from app.models.delivery import EmailMessage, OutboxEvent
from app.providers.email import FakeEmailProvider
from app.services.outbox import (
    LEASE_SECONDS,
    backoff,
    now_utc,
    process_due,
    process_event,
    renew_lease,
    requeue_failed,
    worker_status,
)


def test_crash_recovery_and_fencing(client, database_engine):
    _, key = setup(client)
    email_id = UUID(
        client.post("/v1/emails", json=PAYLOAD, headers={"X-API-Key": key["key"]}).json()["id"]
    )
    factory = client.app.state.session_factory
    with factory() as db:
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.email_id == email_id))
        event.state = "leased"
        event.lease_until = now_utc() + timedelta(seconds=LEASE_SECONDS)
        event.lease_token = uuid4()
        stale_token = event.lease_token
        event_id = event.id
        db.commit()
        assert not process_event(factory, FakeEmailProvider(), event_id)
        with factory() as db:
            event = db.get(OutboxEvent, event_id)
            event.lease_until = now_utc() - timedelta(seconds=1)
            db.commit()
            provider = FakeEmailProvider()
            assert process_event(factory, provider, event_id)
            assert not renew_lease(factory, event_id, stale_token)
            assert not process_event(factory, provider, event_id)
            assert len(provider.submitted_messages) == 1
            with factory() as db:
                assert db.get(EmailMessage, email_id).status == "sent"
                assert db.get(OutboxEvent, event_id).lease_token is None


def test_manual_recovery_and_status(client, database_engine):
    _, key = setup(client)
    email_id = UUID(
        client.post("/v1/emails", json=PAYLOAD, headers={"X-API-Key": key["key"]}).json()["id"]
    )
    factory = client.app.state.session_factory
    assert worker_status(factory)["due"] == 1
    with factory() as db:
        message = db.get(EmailMessage, email_id)
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.email_id == email_id))
        message.status = "failed"
        event.state = "done"
        db.commit()
        assert worker_status(factory)["failed"] == 1
        assert requeue_failed(factory, email_id)
        assert not requeue_failed(factory, email_id)
        assert process_due(factory, FakeEmailProvider()) == 1
        assert worker_status(factory)["failed"] == 0


def test_concurrent_workers_submit_only_once(tmp_path):
    """File-backed SQLite uses separate connections; PostgreSQL test runs separately."""
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'workers.db'}", pool_pre_ping=True)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    # Foreign keys are off in this focused concurrency fixture; API tests cover the FK path.
    email_id, event_id = uuid4(), uuid4()
    with factory() as db:
        db.add(
            EmailMessage(
                id=email_id,
                organization_id=uuid4(),
                api_key_id=None,
                request_hash="x" * 64,
                sender="from@example.com",
                recipients='["to@example.com"]',
                subject="Test",
                text_body="Test",
                status="accepted",
                attempt_count=0,
            )
        )
        db.add(OutboxEvent(id=event_id, email_id=email_id, state="pending"))
        db.commit()

        entered, release = Event(), Event()

        class BlockingProvider(FakeEmailProvider):
            def submit(self, message):
                entered.set()
                assert release.wait(10)
                return super().submit(message)

        provider = BlockingProvider()
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(process_event, factory, provider, event_id)
            assert entered.wait(10)
            second = executor.submit(process_event, factory, provider, event_id)
            assert second.result(timeout=10) is False
            release.set()
            assert first.result(timeout=10) is True
            with Session(engine) as db:
                assert db.get(EmailMessage, email_id).attempt_count == 1
                assert len(provider.submitted_messages) == 1
                engine.dispose()


def test_provider_neutral_stable_idempotency_key(client):
    from app.providers.email import IdempotentFakeEmailProvider

    _, key = setup(client)
    email_id = UUID(
        client.post("/v1/emails", json=PAYLOAD, headers={"X-API-Key": key["key"]}).json()["id"]
    )
    factory = client.app.state.session_factory
    with factory() as db:
        event_id = db.scalar(select(OutboxEvent.id).where(OutboxEvent.email_id == email_id))
        provider = IdempotentFakeEmailProvider()
        assert process_event(factory, provider, event_id)
        # Simulate provider acceptance followed by a lost DB completion. The stable
        # ID lets a cooperating provider return the previous receipt on recovery.
        with factory() as db:
            event = db.get(OutboxEvent, event_id)
            event.state = "leased"
            event.lease_until = now_utc() - timedelta(seconds=1)
            event.lease_token = uuid4()
            db.commit()
            assert process_event(factory, provider, event_id)
            assert len(provider.submitted_messages) == 1
            assert provider.submitted_messages[0].idempotency_key == str(email_id)


def test_stale_worker_cannot_overwrite_replacement_claim(client):
    _, key = setup(client)
    email_id = UUID(
        client.post("/v1/emails", json=PAYLOAD, headers={"X-API-Key": key["key"]}).json()["id"]
    )
    factory = client.app.state.session_factory
    with factory() as db:
        event_id = db.scalar(select(OutboxEvent.id).where(OutboxEvent.email_id == email_id))
        entered, release = Event(), Event()

        class PausedProvider(FakeEmailProvider):
            def submit(self, message):
                entered.set()
                assert release.wait(10)
                return super().submit(message)

        provider = PausedProvider()
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(process_event, factory, provider, event_id)
            assert entered.wait(10)
            with factory() as db:
                event = db.get(OutboxEvent, event_id)
                event.lease_token = uuid4()  # newer worker has replaced the expired lease
                event.lease_until = now_utc() - timedelta(seconds=1)
                db.commit()
        release.set()
        assert first.result(timeout=10) is False
    with factory() as db:
        assert db.get(OutboxEvent, event_id).state == "leased"
        assert db.get(EmailMessage, email_id).status == "sending"
    assert process_event(factory, FakeEmailProvider(), event_id)
    with factory() as db:
        assert db.get(EmailMessage, email_id).status == "sent"
        assert db.get(EmailMessage, email_id).attempt_count == 2


def test_backoff_is_seconds_scale_for_transactional_mail():
    """OTP and password-reset mail must retry in seconds, not in minutes."""
    assert backoff(1) == timedelta(seconds=2)
    assert backoff(2) == timedelta(seconds=5)
    assert backoff(3) == timedelta(seconds=15)
    assert backoff(4) == timedelta(seconds=60)
    assert backoff(5) == timedelta(seconds=300)
    # Unknown attempts exceed the bounded attempt count but must stay sane.
    assert backoff(99) == timedelta(seconds=3600)
    assert backoff(0) == timedelta(seconds=2)
    assert backoff(-3) == timedelta(seconds=2)
