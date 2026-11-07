"""Phase 3 API, tenant isolation and outbox regression."""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_auth import login, register

from app.models.delivery import APIKey, EmailMessage, OutboxEvent
from app.providers.email import SimulatedEmailProvider
from app.services.outbox import now_utc, process_due, process_event

PAYLOAD = {
    "from": "sender@example.com",
    "to": ["receiver@example.com"],
    "subject": "Hello",
    "text_body": "Hello there",
}


def setup(client, email="alice@example.com", name="Alice"):
    org = register(client, email=email, name=name).json()["organization"]["id"]
    login(client, email=email)
    created = client.post(f"/v1/organizations/{org}/api-keys", json={"name": "Test"})
    assert created.status_code == 201, created.text
    return org, created.json()


def test_key_lifecycle_and_authentication(client, database_engine):
    org, created = setup(client)
    raw = created["key"]
    assert raw.startswith("mfk_")
    assert "key_hash" not in str(created)
    with Session(database_engine) as db:
        key = db.get(APIKey, UUID(created["id"]))
        assert key.key_hash != raw and len(key.key_hash) == 64
        listing = client.get(f"/v1/organizations/{org}/api-keys")
        assert listing.status_code == 200
        assert raw not in listing.text and "key_hash" not in listing.text
        assert client.post("/v1/emails", json=PAYLOAD).status_code == 401
        assert (
            client.post("/v1/emails", json=PAYLOAD, headers={"X-API-Key": "mfk_bad"}).status_code
            == 401
        )
        headers = {"X-API-Key": raw}
        assert client.post("/v1/emails", json=PAYLOAD, headers=headers).status_code == 202
        assert (
            client.post(f"/v1/organizations/{org}/api-keys/{created['id']}/revoke").status_code
            == 200
        )
        assert client.post("/v1/emails", json=PAYLOAD, headers=headers).status_code == 401
        with Session(database_engine) as db:
            key = db.get(APIKey, UUID(created["id"]))
            key.is_active = True
            key.revoked_at = None
            db.commit()
            key.is_active = False
            db.commit()
            assert client.get("/v1/emails", headers=headers).status_code == 401
            # The key is referenced by an email, so deletion is deliberately restricted.


def test_key_deletion_and_owner_isolation(client):
    org, created = setup(client)
    assert client.delete(f"/v1/organizations/{org}/api-keys/{created['id']}").status_code == 204
    assert client.get("/v1/emails", headers={"X-API-Key": created["key"]}).status_code == 401
    other_org, other = setup(client, "bob@example.com", "Bob")
    assert client.get(f"/v1/organizations/{org}/api-keys").status_code == 404
    assert (
        client.post(f"/v1/organizations/{org}/api-keys", json={"name": "intruder"}).status_code
        == 404
    )
    assert (
        client.delete(f"/v1/organizations/{other_org}/api-keys/{created['id']}").status_code == 404
    )
    assert other["key"] != created["key"]


def test_submit_idempotency_and_tenant_reads(client, database_engine):
    org, key = setup(client)
    headers = {"X-API-Key": key["key"], "Idempotency-Key": "request-1"}
    first = client.post("/v1/emails", json=PAYLOAD, headers=headers)
    again = client.post("/v1/emails", json=PAYLOAD, headers=headers)
    assert first.status_code == again.status_code == 202
    assert first.json()["id"] == again.json()["id"]
    assert first.json()["status"] == "accepted"
    assert (
        client.post("/v1/emails", json={**PAYLOAD, "subject": "Other"}, headers=headers).status_code
        == 409
    )
    with Session(database_engine) as db:
        assert db.scalar(select(func.count()).select_from(EmailMessage)) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1
    assert client.get("/v1/emails", headers=headers).json()[0]["id"] == first.json()["id"]
    assert client.get(f"/v1/emails/{first.json()['id']}", headers=headers).status_code == 200
    _, other = setup(client, "bob@example.com", "Bob")
    other_headers = {"X-API-Key": other["key"]}
    assert client.get("/v1/emails", headers=other_headers).json() == []
    assert client.get(f"/v1/emails/{first.json()['id']}", headers=other_headers).status_code == 404
    assert org != other["organization_id"]


@pytest.mark.parametrize(
    "changes",
    [
        {"to": []},
        {"to": ["invalid"]},
        {"subject": ""},
        {"text_body": None},
        {"text_body": "x" * 100_001},
        {"to": ["x@example.com"] * 51},
        {"attachments": ["unsupported"]},
    ],
)
def test_email_validation(client, changes):
    _, key = setup(client)
    response = client.post(
        "/v1/emails", json={**PAYLOAD, **changes}, headers={"X-API-Key": key["key"]}
    )
    assert response.status_code == 422


def test_outbox_success_failure_retry_and_duplicate_execution(client, database_engine):
    _, key = setup(client)
    headers = {"X-API-Key": key["key"]}
    message_id = UUID(client.post("/v1/emails", json=PAYLOAD, headers=headers).json()["id"])
    with Session(database_engine) as db:
        event_id = db.scalar(select(OutboxEvent.id).where(OutboxEvent.email_id == message_id))
    factory = client.app.state.session_factory
    provider = SimulatedEmailProvider(["temporary", "success"])
    assert process_event(factory, provider, event_id)
    assert not process_event(factory, provider, event_id)
    with Session(database_engine) as db:
        email = db.get(EmailMessage, message_id)
        assert email.status == "queued" and email.attempt_count == 1
        event = db.get(OutboxEvent, event_id)
        assert event.next_attempt_at.replace(tzinfo=now_utc().tzinfo) > now_utc() - timedelta(
            minutes=1
        )
        event.next_attempt_at = now_utc() - timedelta(seconds=1)
        db.commit()
    assert process_due(factory, provider) == 1
    assert process_due(factory, provider) == 0
    with Session(database_engine) as db:
        email = db.get(EmailMessage, message_id)
        assert email.status == "sent" and email.attempt_count == 2
        assert email.provider == "fake" and email.provider_message_id
    assert len(provider.submitted_messages) == 1
    second_id = UUID(
        client.post("/v1/emails", json={**PAYLOAD, "subject": "Reject"}, headers=headers).json()[
            "id"
        ]
    )
    with Session(database_engine) as db:
        second_event = db.scalar(select(OutboxEvent.id).where(OutboxEvent.email_id == second_id))
    reject = SimulatedEmailProvider(["permanent"])
    assert process_event(factory, reject, second_event)
    assert not process_event(factory, reject, second_event)
    with Session(database_engine) as db:
        assert db.get(EmailMessage, second_id).status == "failed"
        assert db.get(EmailMessage, second_id).attempt_count == 1


def test_delete_key_after_submission_keeps_email_record(client, database_engine):
    _, key = setup(client)
    sent = client.post("/v1/emails", json=PAYLOAD, headers={"X-API-Key": key["key"]})
    assert sent.status_code == 202
    assert (
        client.delete(
            f"/v1/organizations/{key['organization_id']}/api-keys/{key['id']}"
        ).status_code
        == 204
    )
    with Session(database_engine) as db:
        email = db.get(EmailMessage, UUID(sent.json()["id"]))
        assert email is not None and email.api_key_id is None
        assert db.scalar(select(OutboxEvent.id).where(OutboxEvent.email_id == email.id))


def test_bounded_retry_stops_after_five_attempts(client, database_engine):
    _, key = setup(client)
    sent = client.post("/v1/emails", json=PAYLOAD, headers={"X-API-Key": key["key"]})
    email_id = UUID(sent.json()["id"])
    with Session(database_engine) as db:
        event_id = db.scalar(select(OutboxEvent.id).where(OutboxEvent.email_id == email_id))
    provider = SimulatedEmailProvider(["temporary"] * 6)
    for attempt in range(5):
        if attempt:
            with Session(database_engine) as db:
                db.get(OutboxEvent, event_id).next_attempt_at = now_utc() - timedelta(seconds=1)
                db.commit()
        assert process_event(client.app.state.session_factory, provider, event_id)
    assert not process_event(client.app.state.session_factory, provider, event_id)
    with Session(database_engine) as db:
        email = db.get(EmailMessage, email_id)
        assert email.status == "failed" and email.attempt_count == 5
        assert db.get(OutboxEvent, event_id).state == "done"
    assert provider.calls == 5


def test_member_cannot_manage_keys(client, database_engine):
    from app.models import OrganizationMembership, User

    org, key = setup(client)
    assert register(client, "bob@example.com", "Bob").status_code == 201
    with Session(database_engine) as db:
        bob = db.scalar(select(User).where(User.email == "bob@example.com"))
        db.add(OrganizationMembership(organization_id=UUID(org), user_id=bob.id, role="member"))
        db.commit()
        login(client, "bob@example.com")
        assert client.get(f"/v1/organizations/{org}/api-keys").status_code == 404
        assert (
            client.post(f"/v1/organizations/{org}/api-keys", json={"name": "No"}).status_code == 404
        )
        assert (
            client.post(f"/v1/organizations/{org}/api-keys/{key['id']}/revoke").status_code == 404
        )
        assert client.delete(f"/v1/organizations/{org}/api-keys/{key['id']}").status_code == 404


def test_outbox_insert_failure_rolls_back_email(client, database_engine):
    from sqlalchemy import event

    _, key = setup(client)

    def fail_outbox(_mapper, _connection, _target):
        from sqlalchemy.exc import OperationalError

        raise OperationalError("INSERT outbox", {}, Exception("simulated write failure"))

    event.listen(OutboxEvent, "before_insert", fail_outbox)
    try:
        response = client.post("/v1/emails", json=PAYLOAD, headers={"X-API-Key": key["key"]})
    finally:
        event.remove(OutboxEvent, "before_insert", fail_outbox)
    assert response.status_code == 503
    with Session(database_engine) as db:
        assert db.scalar(select(func.count()).select_from(EmailMessage)) == 0
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 0
