"""Phase 7b: daily quota, per-recipient guard and the usage endpoint.

The behaviours that matter, in order of how badly they break production:

1. A tenant cannot send past its plan's daily email limit.
2. Two concurrent sends cannot both take the last slot.
3. An idempotent replay does not consume quota twice.
4. One address cannot be bombed past the per-recipient cap (free plans).
5. A refusal writes nothing — no orphan email, no outbox event.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import enable_sending
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from test_auth import login, register

from app.models.delivery import EmailMessage, OutboxEvent
from app.models.identity import User
from app.models.organization import Organization
from app.models.quota import (
    DEFAULT_PLANS,
    RecipientDailyCount,
    SendingPlan,
    UsageDaily,
)
from app.security.passwords import hash_password
from app.services.organizations import add_organization_with_owner
from app.services.quota import (
    PlanMissing,
    QuotaExceeded,
    current_usage,
    effective_limit,
    load_limit,
    recipient_digest,
    reserve_send,
)

SENDER_DOMAIN = "mailer.example.com"
PAYLOAD = {
    "from": f"noreply@{SENDER_DOMAIN}",
    "to": ["receiver@example.com"],
    "subject": "Hello",
    "text_body": "Hello there",
}


def setup(client, email="quota@example.com", name="Quota"):
    org = register(client, email=email, name=name).json()["organization"]["id"]
    login(client, email=email)
    enable_sending(client, org, SENDER_DOMAIN)
    key = client.post(f"/v1/organizations/{org}/api-keys", json={"name": "Test"}).json()["key"]
    return org, {"X-API-Key": key}


def set_plan(engine, org_id, **limits):
    """Give one tenant a tiny plan so limit tests stay readable and fast."""
    slug = f"test-{org_id[:8]}"
    with Session(engine) as db:
        default = db.get(SendingPlan, "free")
        db.add(
            SendingPlan(
                slug=slug,
                name="Test",
                daily_email_limit=limits.get("emails", 3),
                daily_recipient_limit=limits.get("recipients", 3),
                max_recipients_per_email=limits.get("per_email", 5),
                per_recipient_daily_limit=limits.get("per_recipient", 0),
                price_cents_usd=0,
            )
        )
        organization = db.get(Organization, default and org_id)
        organization.plan = slug
        db.commit()
    return slug


# --------------------------------------------------------------------------- api


def test_free_plan_caps_daily_emails(client, database_engine):
    org, headers = setup(client)
    with Session(database_engine) as db:
        free = db.get(SendingPlan, "free")
        assert free.daily_email_limit == 50

    for _ in range(2):
        assert client.post("/v1/emails", json=PAYLOAD, headers=headers).status_code == 202

    # Shrink the plan rather than sending 50 emails: same code path, less noise.
    with Session(database_engine) as db:
        db.execute(
            update(SendingPlan).where(SendingPlan.slug == "free").values(daily_email_limit=2)
        )
        db.commit()

    refused = client.post("/v1/emails", json=PAYLOAD, headers=headers)
    assert refused.status_code == 429
    body = refused.json()["error"]
    assert body["code"] == "email_quota_exceeded"
    assert "2" in body["message"]
    assert refused.headers["X-Quota-Remaining"] == "0"
    assert refused.headers["Retry-After"] == "3600"


def test_refusal_writes_nothing(client, database_engine):
    _, headers = setup(client)
    with Session(database_engine) as db:
        db.execute(
            update(SendingPlan).where(SendingPlan.slug == "free").values(daily_email_limit=0 + 1)
        )
        db.commit()
    assert client.post("/v1/emails", json=PAYLOAD, headers=headers).status_code == 202

    assert client.post("/v1/emails", json=PAYLOAD, headers=headers).status_code == 429

    with Session(database_engine) as db:
        assert db.scalar(select(func.count()).select_from(EmailMessage)) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1


def test_idempotent_replay_does_not_consume_quota_twice(client, database_engine):
    _, headers = setup(client)
    with Session(database_engine) as db:
        db.execute(
            update(SendingPlan).where(SendingPlan.slug == "free").values(daily_email_limit=1)
        )
        db.commit()
    headers = {**headers, "Idempotency-Key": "same-request"}

    first = client.post("/v1/emails", json=PAYLOAD, headers=headers)
    assert first.status_code == 202
    replay = client.post("/v1/emails", json=PAYLOAD, headers=headers)
    assert replay.status_code == 202
    assert replay.json()["id"] == first.json()["id"]

    with Session(database_engine) as db:
        usage = db.scalar(select(UsageDaily))
        assert usage.emails_sent == 1


def test_conflicting_idempotent_replay_still_conflicts(client, database_engine):
    _, headers = setup(client)
    headers = {**headers, "Idempotency-Key": "same-request"}
    assert client.post("/v1/emails", json=PAYLOAD, headers=headers).status_code == 202
    changed = {**PAYLOAD, "subject": "Different"}
    assert client.post("/v1/emails", json=changed, headers=headers).status_code == 409


def test_recipient_limit_counts_recipients_not_emails(client, database_engine):
    _, headers = setup(client)
    with Session(database_engine) as db:
        db.execute(
            update(SendingPlan)
            .where(SendingPlan.slug == "free")
            .values(daily_email_limit=10, daily_recipient_limit=3, max_recipients_per_email=5)
        )
        db.commit()

    two = {**PAYLOAD, "to": ["a@example.com", "b@example.com"]}
    assert client.post("/v1/emails", json=two, headers=headers).status_code == 202

    # One email left but only one recipient slot: a two-recipient send must fail.
    refused = client.post("/v1/emails", json=two, headers=headers)
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "recipient_quota_exceeded"


def test_too_many_recipients_per_email_on_free_plan(client, database_engine):
    _, headers = setup(client)
    many = {**PAYLOAD, "to": [f"user{index}@example.com" for index in range(6)]}
    refused = client.post("/v1/emails", json=many, headers=headers)
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "too_many_recipients"
    assert refused.headers["X-Quota-Max-Recipients"] == "5"


def test_per_recipient_daily_limit_blocks_otp_bombing(client, database_engine):
    org, headers = setup(client)
    with Session(database_engine) as db:
        db.execute(
            update(SendingPlan)
            .where(SendingPlan.slug == "free")
            .values(
                daily_email_limit=100,
                daily_recipient_limit=100,
                per_recipient_daily_limit=3,
            )
        )
        db.commit()

    victim = {**PAYLOAD, "to": ["victim@example.com"]}
    for _ in range(3):
        assert client.post("/v1/emails", json=victim, headers=headers).status_code == 202

    refused = client.post("/v1/emails", json=victim, headers=headers)
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "recipient_daily_limit_exceeded"
    assert refused.headers["X-Quota-Per-Recipient"] == "3"

    # A different address is unaffected: the guard is per recipient, not global.
    other = {**PAYLOAD, "to": ["someone-else@example.com"]}
    assert client.post("/v1/emails", json=other, headers=headers).status_code == 202

    with Session(database_engine) as db:
        assert (
            db.get(
                RecipientDailyCount,
                {
                    "organization_id": UUID(org),
                    "recipient_hash": recipient_digest("victim@example.com"),
                    "usage_date": datetime.now(UTC).date(),
                },
            ).count
            == 3
        )


def test_repeated_recipient_in_one_request_costs_one_slot(client, database_engine):
    _, headers = setup(client)
    with Session(database_engine) as db:
        db.execute(
            update(SendingPlan)
            .where(SendingPlan.slug == "free")
            .values(per_recipient_daily_limit=1, max_recipients_per_email=5)
        )
        db.commit()
    duplicate = {**PAYLOAD, "to": ["dup@example.com", "dup@example.com"]}
    assert client.post("/v1/emails", json=duplicate, headers=headers).status_code == 202
    assert client.post("/v1/emails", json=duplicate, headers=headers).status_code == 429


def test_usage_endpoint_reports_limits_and_consumption(client, database_engine):
    org, headers = setup(client)
    assert client.post("/v1/emails", json=PAYLOAD, headers=headers).status_code == 202

    usage = client.get("/v1/emails/usage", headers=headers)
    assert usage.status_code == 200
    body = usage.json()
    assert body["plan"] == "free"
    assert body["limit"]["daily_emails"] == 50
    assert body["limit"]["per_recipient_daily_limit"] == 10
    assert body["used"] == {"emails": 1, "recipients": 1}
    assert body["remaining"] == {"emails": 49, "recipients": 49}
    assert usage.headers["Cache-Control"] == "no-store"


def test_usage_is_tenant_scoped(client, database_engine):
    _, first = setup(client, email="one@example.com", name="One")
    assert client.post("/v1/emails", json=PAYLOAD, headers=first).status_code == 202

    _, second = setup(client, email="two@example.com", name="Two")
    body = client.get("/v1/emails/usage", headers=second).json()
    assert body["used"] == {"emails": 0, "recipients": 0}


def test_usage_today_only_resets_at_utc_midnight(client, database_engine):
    org, headers = setup(client)
    assert client.post("/v1/emails", json=PAYLOAD, headers=headers).status_code == 202

    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    with Session(database_engine) as db:
        db.add(
            UsageDaily(
                organization_id=UUID(org),
                usage_date=yesterday,
                emails_sent=50,
                recipients_sent=50,
            )
        )
        db.commit()

    # Yesterday's exhaustion must not leak into today.
    body = client.get("/v1/emails/usage", headers=headers).json()
    assert body["used"]["emails"] == 1
    assert client.post("/v1/emails", json=PAYLOAD, headers=headers).status_code == 202


def test_unknown_plan_is_a_service_error_not_a_bypass(client, database_engine, monkeypatch):
    """If a tenant's plan row vanished, sending must fail closed rather than open.

    Pointing the row at a missing slug is rejected by the foreign key, so the
    deletion is simulated at the loader instead — the behaviour under test is the
    API's response to a plan that cannot be resolved.
    """
    _, headers = setup(client)

    def missing_plan(_db, _organization):
        raise PlanMissing("plan not found")

    monkeypatch.setattr("app.api.emails.load_limit", missing_plan)
    response = client.post("/v1/emails", json=PAYLOAD, headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "plan_not_configured"


def test_unknown_plan_blocks_the_usage_endpoint_too(client, database_engine, monkeypatch):
    _, headers = setup(client)

    def missing_plan(_db, _organization):
        raise PlanMissing("plan not found")

    monkeypatch.setattr("app.api.emails.usage_summary", missing_plan)
    response = client.get("/v1/emails/usage", headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "plan_not_configured"


# ------------------------------------------------------------------------ unit


def make_tenant(engine, **limits):
    """A real owner/user pair so the organization ownership guard stays satisfied."""
    slug = f"unit-{uuid4().hex[:8]}"
    with Session(engine) as db:
        user = User(
            name="Owner",
            email=f"{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("Correct horse battery staple 2026!"),
        )
        db.add(user)
        db.add(
            SendingPlan(
                slug=slug,
                name="Unit",
                daily_email_limit=limits.get("emails", 1),
                daily_recipient_limit=limits.get("recipients", 1),
                max_recipients_per_email=limits.get("per_email", 5),
                per_recipient_daily_limit=limits.get("per_recipient", 0),
                price_cents_usd=0,
            )
        )
        db.flush()
        organization = add_organization_with_owner(db, name="Unit org", owner_user_id=user.id)
        organization.plan = slug
        db.commit()
        return organization.id, slug


def test_last_slot_cannot_be_taken_twice(database_engine):
    """Two reservations of a one-slot quota: the second must be refused."""
    org_id, _ = make_tenant(database_engine, emails=1, recipients=1)
    with Session(database_engine) as db:
        organization = db.get(Organization, org_id)
        limit = load_limit(db, organization)

        reserve_send(db, organization=organization, recipients=["a@example.com"], limit=limit)
        with pytest.raises(QuotaExceeded) as exc:
            reserve_send(db, organization=organization, recipients=["b@example.com"], limit=limit)
        assert exc.value.code == "email_quota_exceeded"
        assert current_usage(db, org_id).emails_sent == 1


def test_unknown_plan_fails_closed(database_engine):
    """A tenant pointing at a deleted plan must error, never send unlimited."""
    org_id, _ = make_tenant(database_engine)
    with Session(database_engine) as db:
        organization = db.get(Organization, org_id)
        # The column is FK-constrained, so mutate the in-memory value only. The
        # session is expired so the attribute is never flushed by an autoflush.
        db.expunge(organization)
        organization.plan = "plan-that-does-not-exist"
        with pytest.raises(PlanMissing):
            load_limit(db, organization)


def test_plan_overrides_win_but_cannot_remove_a_limit(database_engine):
    with Session(database_engine) as db:
        plan = db.get(SendingPlan, "free")
        organization = Organization(name="Override", owner_user_id=None, plan="free")
        organization.plan_overrides = {"daily_email_limit": 500, "per_recipient_daily_limit": 0}
        assert effective_limit(organization, plan).daily_email_limit == 500
        assert effective_limit(organization, plan).per_recipient_daily_limit == 0

        organization.plan_overrides = {"daily_email_limit": -5}
        assert effective_limit(organization, plan).daily_email_limit == plan.daily_email_limit
        assert effective_limit(organization, plan).per_recipient_daily_limit == (
            plan.per_recipient_daily_limit
        )


def test_recipient_digest_is_stable_and_case_insensitive():
    assert recipient_digest("  Victim@Example.COM ") == recipient_digest("victim@example.com")
    assert recipient_digest("a@example.com") != recipient_digest("b@example.com")
    assert len(recipient_digest("a@example.com")) == 64


def test_every_paid_plan_can_afford_its_own_worst_case():
    """A customer who maxes a plan must not cost more than the plan can pay for.

    Quota is enforced per day, so daily x 30 is the monthly ceiling. At $0.10 per
    1,000 emails that is daily x 30 / 1000 x $0.10 of SES. If that ever exceeds the
    price, the plan is a loss-making subscription and one heavy customer hurts more
    than ten light ones help.
    """
    ses_per_email = 0.10 / 1_000
    for plan in DEFAULT_PLANS:
        cents = int(plan["price_cents_usd"])
        if cents == 0:
            continue
        monthly_emails = int(plan["daily_email_limit"]) * 30
        ses_cost = monthly_emails * ses_per_email
        assert ses_cost <= cents / 100, (
            f"{plan['slug']}: {monthly_emails:,} emails/month costs "
            f"${ses_cost:.2f} of SES but the plan only earns ${cents / 100:.2f}"
        )
