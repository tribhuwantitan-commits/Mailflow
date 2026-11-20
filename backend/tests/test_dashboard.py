"""Phase 9: the dashboard summary endpoint.

The dashboard has one job order and the tests follow it. A brand-new tenant must see
which step they are stuck on; a working tenant must see quota and deliverability
without being able to read another tenant's numbers; and the deliverability rates
must agree with the pause thresholds, because a dashboard that says "fine" while the
worker is about to pause the account is worse than no dashboard.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from conftest import enable_sending
from test_auth import login, register

from app.models.delivery import EmailMessage
from app.models.delivery_events import DeliveryEvent, Suppression

SENDER_DOMAIN = "dash.example.com"
PAYLOAD = {
    "from": f"noreply@{SENDER_DOMAIN}",
    "to": ["receiver@example.com"],
    "subject": "Hello",
    "text_body": "Hello there",
}


def setup(client, email="dash@example.com", name="Dash"):
    org = register(client, email=email, name=name).json()["organization"]["id"]
    login(client, email=email)
    return org


def stats_url(org: str, **params) -> str:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"/v1/organizations/{org}/stats" + (f"?{query}" if query else "")


def test_new_tenant_sees_the_first_unfinished_step(client, database_engine):
    """Nothing sent yet: the checklist says so instead of showing empty charts."""
    org = setup(client)
    body = client.get(stats_url(org)).json()

    assert body["activation"]["complete"] is False
    assert body["activation"]["first_delivered_at"] is None
    assert [step["key"] for step in body["activation"]["steps"]] == [
        "domain",
        "api_key",
        "send",
        "delivered",
    ]
    assert [step["done"] for step in body["activation"]["steps"]] == [False, False, False, False]
    assert body["used"] == {"daily_emails": 0, "monthly_emails": 0}
    assert body["volume"][-1]["emails"] == 0


def test_activation_completes_only_after_delivery_is_confirmed(client, database_engine):
    """Sending is not activation. A mailbox receiving it is."""
    org = setup(client, email="activate@example.com", name="Activate")
    enable_sending(client, org, SENDER_DOMAIN)
    key = client.post(f"/v1/organizations/{org}/api-keys", json={"name": "Dash"}).json()["key"]

    created = client.post("/v1/emails", json=PAYLOAD, headers={"X-API-Key": key})
    assert created.status_code == 202, created.text
    email_id = UUID(created.json()["id"])

    body = client.get(stats_url(org)).json()
    steps = {step["key"]: step["done"] for step in body["activation"]["steps"]}
    assert steps["domain"] is True
    assert steps["api_key"] is True
    assert steps["send"] is True
    assert steps["delivered"] is False
    assert body["activation"]["complete"] is False

    factory = client.app.state.session_factory
    with factory() as db:
        message = db.get(EmailMessage, email_id)
        message.delivered_at = datetime.now(UTC)
        db.add(
            DeliveryEvent(
                organization_id=UUID(org),
                email_id=email_id,
                provider_event_id="dash-delivery-1",
                provider_message_id=message.provider_message_id or "pm-1",
                event_type="Delivery",
                recipient="receiver@example.com",
                provider_event_at=datetime.now(UTC),
            )
        )
        db.commit()

    body = client.get(stats_url(org)).json()
    assert body["activation"]["complete"] is True
    assert body["activation"]["first_delivered_at"] is not None
    assert all(step["done"] for step in body["activation"]["steps"])


def test_deliverability_rates_match_the_ingest_story(client, database_engine):
    """The percentages here must be the same arithmetic the pause decision uses."""
    org = setup(client, email="rates@example.com", name="Rates")
    factory = client.app.state.session_factory
    now = datetime.now(UTC)
    with factory() as db:
        for index in range(90):
            db.add(
                DeliveryEvent(
                    organization_id=UUID(org),
                    provider_event_id=f"ok-{index}",
                    event_type="Delivery",
                    provider_event_at=now,
                    received_at=now,
                )
            )
        for index in range(10):
            db.add(
                DeliveryEvent(
                    organization_id=UUID(org),
                    provider_event_id=f"bad-{index}",
                    event_type="Bounce",
                    provider_event_at=now,
                    received_at=now,
                )
            )
        db.add(
            DeliveryEvent(
                organization_id=UUID(org),
                provider_event_id="complaint-1",
                event_type="Complaint",
                provider_event_at=now,
                received_at=now,
            )
        )
        db.add(
            Suppression(organization_id=UUID(org), recipient="gone@example.com", reason="bounce")
        )
        db.commit()

    body = client.get(stats_url(org)).json()
    delivery = body["deliverability"]
    assert delivery["delivered"] == 90
    assert delivery["bounced"] == 10
    assert delivery["complained"] == 1
    assert delivery["suppressed"] == 1
    assert delivery["judged"] == 100
    # 10 bounces in 100 judged sends is the 10% that trips the 5% pause threshold.
    assert delivery["bounce_rate"] == 0.1
    assert delivery["complaint_rate"] == round(1 / 91, 4)


def test_events_outside_the_window_are_not_counted(client, database_engine):
    """A rolling window, not a lifetime total -- old bounces must not haunt a tenant."""
    org = setup(client, email="window@example.com", name="Window")
    factory = client.app.state.session_factory
    old = datetime.now(UTC) - timedelta(days=60)
    with factory() as db:
        db.add(
            DeliveryEvent(
                organization_id=UUID(org),
                provider_event_id="ancient",
                event_type="Bounce",
                provider_event_at=old,
                received_at=old,
            )
        )
        db.commit()

    assert client.get(stats_url(org)).json()["deliverability"]["bounced"] == 0
    assert client.get(stats_url(org, window_days=90)).json()["deliverability"]["bounced"] == 1


def test_stats_are_tenant_scoped(client, database_engine):
    """Another tenant's organization id must be a 404, not a peek."""
    setup(client, email="owner-one@example.com", name="One")
    other_org = setup(client, email="owner-two@example.com", name="Two")

    login(client, "owner-one@example.com")
    assert client.get(stats_url(other_org)).status_code == 404


def test_stats_require_a_session(client, database_engine):
    org = setup(client, email="anon@example.com", name="Anon")
    client.cookies.clear()
    assert client.get(stats_url(org)).status_code == 401


def test_volume_series_is_zero_filled_and_oldest_first(client, database_engine):
    """Gaps drawn as gaps hide the failure that matters: a sudden drop to nothing."""
    org = setup(client, email="series@example.com", name="Series")
    key = client.post(f"/v1/organizations/{org}/api-keys", json={"name": "S"}).json()["key"]
    enable_sending(client, org, SENDER_DOMAIN)
    assert client.post("/v1/emails", json=PAYLOAD, headers={"X-API-Key": key}).status_code == 202

    body = client.get(stats_url(org, window_days=7)).json()
    volume = body["volume"]
    assert len(volume) == 14
    assert volume == sorted(volume, key=lambda point: point["day"])
    assert volume[-1]["emails"] == 1
    assert sum(point["emails"] for point in volume) == 1


def test_recent_emails_hides_bodies(client, database_engine):
    """The activity list must not carry the expensive column it never displays."""
    org = setup(client, email="activity@example.com", name="Activity")
    key = client.post(f"/v1/organizations/{org}/api-keys", json={"name": "A"}).json()["key"]
    enable_sending(client, org, SENDER_DOMAIN)
    client.post("/v1/emails", json=PAYLOAD, headers={"X-API-Key": key})

    rows = client.get(f"/v1/organizations/{org}/emails").json()
    assert len(rows) == 1
    assert rows[0]["subject"] == "Hello"
    assert rows[0]["status"] == "accepted"
    assert "text_body" not in rows[0]
    assert "html_body" not in rows[0]


def test_overview_reports_both_caps_so_the_daily_bar_cannot_mislead(client, database_engine):
    """50/day and 1,000/month are separate promises and both are on the page."""
    org = setup(client, email="caps@example.com", name="Caps")
    key = client.post(f"/v1/organizations/{org}/api-keys", json={"name": "C"}).json()["key"]
    enable_sending(client, org, SENDER_DOMAIN)
    client.post("/v1/emails", json=PAYLOAD, headers={"X-API-Key": key})

    body = client.get(stats_url(org)).json()
    assert body["plan"] == "free"
    assert body["limit"] == {"daily_emails": 50, "monthly_emails": 1_000}
    assert body["used"] == {"daily_emails": 1, "monthly_emails": 1}
    assert body["remaining"] == {"daily_emails": 49, "monthly_emails": 999}
