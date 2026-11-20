"""Phase 7c: SES event ingest, suppression, auto-pause and retention.

What must hold, in order of how badly it breaks:

1. A hard bounce suppresses that address for that tenant, and only that tenant.
2. SNS redelivery of the same event is a no-op.
3. An event we cannot attribute is not silently dropped.
4. A tenant crossing the bounce threshold is paused before AWS notices.
5. A suppressed recipient or a paused tenant never reaches the provider.
6. Bodies expire; metadata does not.
"""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from conftest import enable_sending
from sqlalchemy import select

from app.models.delivery import EmailMessage
from app.models.delivery_events import DeliveryEvent, Suppression, TenantReputation
from app.models.organization import Organization
from app.providers.email import FakeEmailProvider
from app.services.delivery_events import (
    MIN_SENDS_TO_JUDGE,
    ingest,
    parse_ses_event,
    suppressed_recipients,
    unwrap_sns,
)
from app.services.maintenance import (
    clear_expired_bodies,
    clear_expired_event_payloads,
    purge_counters,
)
from app.services.outbox import process_due

PAYLOAD = {
    "from": "noreply@mailer.example.com",
    "to": ["receiver@example.com"],
    "subject": "Hello",
    "text_body": "Hello there",
}

SENDER_DOMAIN = "mailer.example.com"


def setup(client, email="events@example.com", name="Events"):
    org = register_and_key(client, email, name)
    return org


def register_and_key(client, email, name):
    from test_auth import login, register

    org = register(client, email=email, name=name).json()["organization"]["id"]
    login(client, email=email)
    enable_sending(client, org, SENDER_DOMAIN)
    key = client.post(f"/v1/organizations/{org}/api-keys", json={"name": "Test"}).json()["key"]
    return {"org": org, "headers": {"X-API-Key": key}}


def submit(client, tenant, payload=None):
    response = client.post("/v1/emails", json=payload or PAYLOAD, headers=tenant["headers"])
    assert response.status_code == 202, response.text
    return response.json()


def send_one(client, database_engine, tenant=None):
    """Submit and deliver one message through the fake provider, returning its id."""
    tenant = tenant or setup(client)
    created = submit(client, tenant)
    factory = client.app.state.session_factory
    assert process_due(factory, FakeEmailProvider()) >= 1
    with factory() as db:
        message = db.get(EmailMessage, UUID(created["id"]))
        assert message.provider_message_id
        return tenant, message.id, message.provider_message_id


def sns_envelope(event: dict, message_id: str = "sns-1") -> str:
    return json.dumps(
        {"Type": "Notification", "MessageId": message_id, "Message": json.dumps(event)}
    )


def now_iso() -> str:
    """Event timestamps must be 'now', else counters land on a different day row."""
    return datetime.now(UTC).isoformat()


def ses_event(
    *,
    event_type,
    message_id,
    recipients=(),
    bounce_type=None,
    timestamp=None,
    sns_message_id="sns-1",
    envelope=True,
):
    mail = {
        "timestamp": timestamp or now_iso(),
        "messageId": message_id,
        "destination": list(recipients),
        "source": "noreply@mailer.example.com",
    }
    event = {"eventType": event_type, "mail": mail}
    if event_type == "Bounce":
        event["bounce"] = {
            "bounceType": bounce_type or "Permanent",
            "bounceSubType": "General",
            "bouncedRecipients": [{"emailAddress": address} for address in recipients],
        }
    if event_type == "Complaint":
        event["complaint"] = {
            "complainedRecipients": [{"emailAddress": address} for address in recipients]
        }
    if event_type == "Delivery":
        event["delivery"] = {"recipients": list(recipients), "timestamp": mail["timestamp"]}
    body = json.dumps(event)
    return sns_envelope(json.loads(body), sns_message_id) if envelope else body


# --------------------------------------------------------------------- parsing


def test_unwrap_accepts_sns_envelope_and_bare_event():
    event = {"eventType": "Delivery", "mail": {"messageId": "abc"}}
    envelope_id, raw = unwrap_sns(sns_envelope(event, "sns-99"))
    assert envelope_id == "sns-99"
    assert json.loads(raw)["eventType"] == "Delivery"

    envelope_id, raw = unwrap_sns(json.dumps(event))
    assert envelope_id == ""
    assert json.loads(raw)["eventType"] == "Delivery"


def test_parse_extracts_bounce_details():
    parsed = parse_ses_event(
        ses_event(
            event_type="Bounce",
            message_id="m1",
            recipients=("User@Example.com",),
            bounce_type="Permanent",
            envelope=False,
        )
    )
    assert parsed.event_type == "Bounce"
    assert parsed.bounce_type == "Permanent"
    # Lowercased so suppression lookups match what the transport does.
    assert parsed.recipients == ("user@example.com",)


def test_parse_rejects_junk():
    assert parse_ses_event("not json") is None
    assert parse_ses_event('["a list"]') is None


# ---------------------------------------------------------------------- ingest


def test_delivery_marks_the_message_delivered(client, database_engine):
    _, email_id, provider_id = send_one(client, database_engine)
    factory = client.app.state.session_factory

    with factory() as db:
        result = ingest(
            db,
            ses_event(
                event_type="Delivery",
                message_id=provider_id,
                recipients=("receiver@example.com",),
            ),
        )
        db.commit()
        assert result.stored and result.attributed

    with factory() as db:
        message = db.get(EmailMessage, email_id)
        assert message.status == "delivered"
        assert message.delivered_at is not None
        event = db.scalar(select(DeliveryEvent).where(DeliveryEvent.email_id == email_id))
        assert event.event_type == "Delivery"
        assert event.recipient == "receiver@example.com"


def test_hard_bounce_suppresses_the_recipient(client, database_engine):
    tenant, email_id, provider_id = send_one(client, database_engine)
    factory = client.app.state.session_factory

    with factory() as db:
        result = ingest(
            db,
            ses_event(
                event_type="Bounce",
                message_id=provider_id,
                recipients=("receiver@example.com",),
                bounce_type="Permanent",
            ),
        )
        db.commit()
        assert result.suppressed == 1

    with factory() as db:
        message = db.get(EmailMessage, email_id)
        assert message.status == "bounced"
        assert message.bounce_type == "Permanent"
        assert message.bounced_at is not None
        assert suppressed_recipients(db, UUID(tenant["org"]), ["receiver@example.com"]) == [
            "receiver@example.com"
        ]


def test_soft_bounce_is_recorded_but_not_suppressed(client, database_engine):
    tenant, _, provider_id = send_one(client, database_engine)
    factory = client.app.state.session_factory
    with factory() as db:
        ingest(
            db,
            ses_event(
                event_type="Bounce",
                message_id=provider_id,
                recipients=("soft@example.com",),
                bounce_type="Transient",
            ),
        )
        db.commit()
    with factory() as db:
        assert suppressed_recipients(db, UUID(tenant["org"]), ["soft@example.com"]) == []


def test_complaint_suppresses_the_recipient(client, database_engine):
    tenant, email_id, provider_id = send_one(client, database_engine)
    factory = client.app.state.session_factory
    with factory() as db:
        ingest(
            db,
            ses_event(
                event_type="Complaint", message_id=provider_id, recipients=("angry@example.com",)
            ),
        )
        db.commit()
    with factory() as db:
        assert db.get(EmailMessage, email_id).complained_at is not None
        assert db.get(EmailMessage, email_id).status == "complained"
        assert suppressed_recipients(db, UUID(tenant["org"]), ["angry@example.com"])


def test_redelivered_event_is_a_no_op(client, database_engine):
    _, email_id, provider_id = send_one(client, database_engine)
    factory = client.app.state.session_factory
    body = ses_event(
        event_type="Delivery",
        message_id=provider_id,
        recipients=("receiver@example.com",),
        sns_message_id="sns-abc",
    )

    with factory() as db:
        assert ingest(db, body).stored is True
        db.commit()
    with factory() as db:
        second = ingest(db, body)
        db.commit()
        assert second.stored is False
        assert second.reason == "duplicate"
        assert (
            db.scalar(
                select(DeliveryEvent).where(DeliveryEvent.email_id == email_id)
            ).provider_event_id
            == "sns-abc"
        )
        assert (
            len(db.scalars(select(DeliveryEvent).where(DeliveryEvent.email_id == email_id)).all())
            == 1
        )


def test_unknown_message_id_is_reported_not_stored(client, database_engine):
    factory = client.app.state.session_factory
    with factory() as db:
        result = ingest(db, ses_event(event_type="Delivery", message_id="does-not-exist"))
        db.commit()
        assert result.stored is False
        assert result.attributed is False
        assert result.reason == "unknown_message"


def test_suppression_is_tenant_scoped(client, database_engine):
    first, _, provider_id = send_one(client, database_engine)
    factory = client.app.state.session_factory
    with factory() as db:
        ingest(
            db,
            ses_event(
                event_type="Bounce", message_id=provider_id, recipients=("shared@example.com",)
            ),
        )
        db.commit()

    from test_auth import login, register

    second_org = register(client, email="other@example.com", name="Other").json()["organization"][
        "id"
    ]
    login(client, "other@example.com")
    enable_sending(client, second_org, "other-mailer.example.com")
    with factory() as db:
        # One tenant's bounce must not silence the same address for another tenant.
        assert suppressed_recipients(db, UUID(second_org), ["shared@example.com"]) == []


# ---------------------------------------------------------------- auto-pause


def test_tenant_is_paused_after_crossing_the_bounce_threshold(client, database_engine):
    tenant, _, provider_id = send_one(client, database_engine)
    factory = client.app.state.session_factory

    class Padded:
        """A message id we control, so we can feed a realistic number of events."""

    with factory() as db:
        message = db.scalar(
            select(EmailMessage).where(EmailMessage.provider_message_id == provider_id)
        )
        organization = db.get(Organization, message.organization_id)
        day = datetime.now(UTC).date()
        db.add(
            TenantReputation(
                organization_id=organization.id,
                day=day,
                sent=MIN_SENDS_TO_JUDGE + 1,
                delivered=MIN_SENDS_TO_JUDGE,
                bounced=0,
            )
        )
        db.commit()

    # Push bounces past 5% of judged mail.
    for index in range(6):
        with factory() as db:
            ingest(
                db,
                ses_event(
                    event_type="Bounce",
                    message_id=provider_id,
                    recipients=(f"bad{index}@example.com",),
                    sns_message_id=f"sns-bounce-{index}",
                ),
            )
            db.commit()

    with factory() as db:
        organization = db.get(Organization, UUID(tenant["org"]))
        assert organization.sending_paused_at is not None
        assert "bounce rate" in organization.sending_paused_reason


def test_small_volume_does_not_pause(client, database_engine):
    tenant, _, provider_id = send_one(client, database_engine)
    factory = client.app.state.session_factory
    for index in range(3):
        with factory() as db:
            ingest(
                db,
                ses_event(
                    event_type="Bounce",
                    message_id=provider_id,
                    recipients=(f"tiny{index}@example.com",),
                    sns_message_id=f"sns-tiny-{index}",
                ),
            )
            db.commit()
    with factory() as db:
        # Three bounces out of three sends is 100%, but the sample is far too small
        # to judge a tenant on.
        assert db.get(Organization, UUID(tenant["org"])).sending_paused_at is None


def test_paused_tenant_is_refused_at_submit_and_in_the_worker(client, database_engine):
    tenant, _, _ = send_one(client, database_engine)
    factory = client.app.state.session_factory
    with factory() as db:
        organization = db.get(Organization, UUID(tenant["org"]))
        organization.sending_paused_at = datetime.now(UTC)
        organization.sending_paused_reason = "bounce rate 9/120 above 5%"
        db.commit()

    refused = client.post("/v1/emails", json=PAYLOAD, headers=tenant["headers"])
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "sending_paused"


# ------------------------------------------------------- suppression at send


def test_suppressed_recipient_never_reaches_the_provider(client, database_engine):
    tenant, _, _ = send_one(client, database_engine)
    factory = client.app.state.session_factory
    with factory() as db:
        message = db.scalar(select(EmailMessage))
        db.add(
            Suppression(
                organization_id=message.organization_id,
                recipient="receiver@example.com",
                reason="bounce",
            )
        )
        db.commit()

    created = submit(client, tenant)
    provider = FakeEmailProvider()
    assert process_due(factory, provider) >= 1

    assert provider.submitted_messages == []
    with factory() as db:
        failed = db.get(EmailMessage, UUID(created["id"]))
        assert failed.status == "failed"
        assert failed.error_code == "recipient_suppressed"


def test_unsubscribe_headers_are_sent_when_configured(client, database_engine):
    tenant, _, _ = send_one(client, database_engine)
    factory = client.app.state.session_factory
    submit(client, tenant)

    provider = FakeEmailProvider()
    assert process_due(factory, provider, unsubscribe_mailto="unsub@mailer.example.com") >= 1
    sent = provider.submitted_messages[-1]
    headers = dict(sent.headers)
    assert headers["List-Unsubscribe"].startswith("<mailto:unsub@mailer.example.com")
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_no_unsubscribe_headers_when_unconfigured(client, database_engine):
    tenant, _, _ = send_one(client, database_engine)
    factory = client.app.state.session_factory
    submit(client, tenant)
    provider = FakeEmailProvider()
    process_due(factory, provider)
    assert provider.submitted_messages[-1].headers == ()


# ------------------------------------------------------------------- endpoint


def test_events_endpoint_returns_a_timeline(client, database_engine):
    from test_auth import login, register

    org = register(client, email="timeline@example.com", name="Timeline").json()["organization"][
        "id"
    ]
    login(client, "timeline@example.com")
    enable_sending(client, org, "timeline.example.com")
    key = client.post(f"/v1/organizations/{org}/api-keys", json={"name": "Timeline"}).json()["key"]
    headers = {"X-API-Key": key}

    created = client.post(
        "/v1/emails",
        json={
            "from": "noreply@timeline.example.com",
            "to": ["receiver@example.com"],
            "subject": "Timeline",
            "text_body": "Hello there",
        },
        headers=headers,
    )
    assert created.status_code == 202, created.text
    email_id = UUID(created.json()["id"])

    factory = client.app.state.session_factory
    assert process_due(factory, FakeEmailProvider()) >= 1
    with factory() as db:
        provider_id = db.get(EmailMessage, email_id).provider_message_id
        result = ingest(
            db,
            ses_event(
                event_type="Delivery",
                message_id=provider_id,
                recipients=("receiver@example.com",),
                sns_message_id="t1",
            ),
        )
        db.commit()
        assert result.stored, result

    response = client.get(f"/v1/emails/{email_id}/events", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(email_id)
    assert [event["type"] for event in body["events"]] == ["Delivery"]
    assert body["events"][0]["recipient"] == "receiver@example.com"


def test_events_endpoint_is_tenant_scoped(client, database_engine):
    _, email_id, _ = send_one(client, database_engine)
    other = setup(client, "snoop@example.com", "Snoop")
    assert client.get(f"/v1/emails/{email_id}/events", headers=other["headers"]).status_code == 404


# ------------------------------------------------------------------ retention


def test_expired_bodies_are_cleared_and_metadata_kept(client, database_engine):
    tenant, email_id, _ = send_one(client, database_engine)
    factory = client.app.state.session_factory
    old = datetime.now(UTC) - timedelta(days=45)
    with factory() as db:
        message = db.get(EmailMessage, email_id)
        message.created_at = old
        db.commit()
        cleared = clear_expired_bodies(db, retention_days=30)
        assert cleared == 1

    with factory() as db:
        message = db.get(EmailMessage, email_id)
        assert message.text_body is None and message.html_body is None
        assert message.subject == "Hello"
        assert message.provider_message_id
        assert message.status == "sent"


def test_recent_bodies_are_kept(client, database_engine):
    _, email_id, _ = send_one(client, database_engine)
    factory = client.app.state.session_factory
    with factory() as db:
        assert clear_expired_bodies(db, retention_days=30) == 0
        assert db.get(EmailMessage, email_id).text_body == "Hello there"


def test_event_payloads_are_cleared_but_the_timeline_survives(client, database_engine):
    tenant, email_id, provider_id = send_one(client, database_engine)
    factory = client.app.state.session_factory
    with factory() as db:
        ingest(
            db,
            ses_event(
                event_type="Delivery",
                message_id=provider_id,
                recipients=("receiver@example.com",),
                sns_message_id="payload-1",
            ),
        )
        db.commit()
        event = db.scalars(select(DeliveryEvent)).one()
        event.received_at = datetime.now(UTC) - timedelta(days=30)
        db.commit()

        assert clear_expired_event_payloads(db, retention_days=7) == 1

    with factory() as db:
        event = db.scalars(select(DeliveryEvent)).one()
        # The payload is what costs the storage; everything a timeline needs stays.
        assert event.payload is None
        assert event.event_type == "Delivery"
        assert event.recipient == "receiver@example.com"
        assert event.provider_event_id == "payload-1"

    response = client.get(f"/v1/emails/{email_id}/events", headers=tenant["headers"])
    assert response.status_code == 200
    assert [item["type"] for item in response.json()["events"]] == ["Delivery"]


def test_recent_event_payloads_are_kept(client, database_engine):
    _, _, provider_id = send_one(client, database_engine)
    factory = client.app.state.session_factory
    with factory() as db:
        ingest(
            db,
            ses_event(
                event_type="Delivery",
                message_id=provider_id,
                recipients=("receiver@example.com",),
                sns_message_id="payload-2",
            ),
        )
        db.commit()
        assert clear_expired_event_payloads(db, retention_days=7) == 0
        assert db.scalars(select(DeliveryEvent)).one().payload is not None


def test_counter_purge_respects_each_window(client, database_engine):
    tenant, _, _ = send_one(client, database_engine)
    factory = client.app.state.session_factory
    today = datetime.now(UTC).date()
    with factory() as db:
        from app.models.quota import RecipientDailyCount, UsageDaily

        org_id = UUID(tenant["org"])
        db.add_all(
            [
                UsageDaily(organization_id=org_id, usage_date=today - timedelta(days=200)),
                UsageDaily(organization_id=org_id, usage_date=today - timedelta(days=10)),
                RecipientDailyCount(
                    organization_id=org_id,
                    recipient_hash="x" * 64,
                    usage_date=today - timedelta(days=30),
                ),
                RecipientDailyCount(
                    organization_id=org_id, recipient_hash="y" * 64, usage_date=today
                ),
            ]
        )
        db.commit()
        result = purge_counters(db)
        # Only the 200-day-old row is past the 90-day window; the 10-day-old row and
        # today's (written by the send above) both stay.
        assert result.usage_deleted == 1
        assert result.recipient_counts_deleted == 1

    with factory() as db:
        from app.models.quota import RecipientDailyCount, UsageDaily

        remaining = db.scalars(select(UsageDaily)).all()
        assert len(remaining) == 2
        assert all(row.usage_date >= today - timedelta(days=90) for row in remaining)
        counts = db.scalars(select(RecipientDailyCount)).all()
        # Only the 30-day-old row is past the 7-day guard window; today's row (written
        # by the send above) and the fresh seeded one both stay.
        assert len(counts) == 2
        assert "y" * 64 in {row.recipient_hash for row in counts}
