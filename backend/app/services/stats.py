"""Tenant-facing numbers: activation, volume, and deliverability.

The dashboard exists to answer three questions, in this order:

1. **Have I got email working yet?** Somebody who has not delivered a single message
   cannot use anything else on the page. That is why ``first_delivered_at`` is the
   headline in :func:`activation` rather than a stat among many.
2. **How much of my allowance is gone?** Daily *and* monthly, because the plan is
   capped on both and a customer who only sees the daily bar is surprised twice.
3. **Are my messages being delivered?** Delivered, bounced and complained, with the
   rates that actually get an account paused.

Everything is scoped by organization at the start of each query. None of these
functions takes a caller identity; the route is responsible for proving membership
first, and these helpers must not be reachable without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.delivery import APIKey, EmailMessage
from app.models.delivery_events import DeliveryEvent, Suppression
from app.models.domain import Domain
from app.models.organization import Organization
from app.services.quota import MonthlyUsage, Usage, current_month_usage, current_usage

#: A tenant is "activated" once one message reached a mailbox. Matches the marketing
#: metric: signups are not the funnel, first delivery is.
ACTIVATION_STATUSES = ("sent", "delivered", "bounced", "complained")
#: Statuses that mean SES accepted the message and something happened afterwards.
DELIVERED_STATUSES = ("delivered",)


@dataclass(frozen=True)
class Activation:
    has_verified_domain: bool
    has_api_key: bool
    has_sent_email: bool
    first_delivered_at: datetime | None

    @property
    def complete(self) -> bool:
        return self.first_delivered_at is not None

    def as_steps(self) -> list[dict[str, object]]:
        """Ordered checklist, because the dashboard renders it as a progress list."""
        return [
            {
                "key": "domain",
                "label": "Verify a sending domain",
                "done": self.has_verified_domain,
            },
            {"key": "api_key", "label": "Create an API key", "done": self.has_api_key},
            {
                "key": "send",
                "label": "Send your first email",
                "done": self.has_sent_email,
            },
            {
                "key": "delivered",
                "label": "See it delivered",
                "done": self.first_delivered_at is not None,
            },
        ]


@dataclass(frozen=True)
class Deliverability:
    sent: int
    delivered: int
    bounced: int
    complained: int
    suppressed: int

    @property
    def bounce_rate(self) -> float:
        judged = self.delivered + self.bounced
        return (self.bounced / judged) if judged else 0.0

    @property
    def complaint_rate(self) -> float:
        judged = self.delivered + self.complained
        return (self.complained / judged) if judged else 0.0

    @property
    def judged(self) -> int:
        return self.delivered + self.bounced


def _count(db: Session, model, *conditions) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def activation(db: Session, organization_id: UUID) -> Activation:
    """The four-step checklist, with first delivery as the finish line."""
    has_domain = bool(
        db.scalar(
            select(func.count())
            .select_from(Domain)
            .where(Domain.organization_id == organization_id, Domain.status == "verified")
        )
    )
    has_key = bool(
        db.scalar(
            select(func.count())
            .select_from(APIKey)
            .where(APIKey.organization_id == organization_id, APIKey.revoked_at.is_(None))
        )
    )
    has_sent = bool(_count(db, EmailMessage, EmailMessage.organization_id == organization_id) > 0)
    first_verified_contact = db.scalar(
        select(func.min(DeliveryEvent.provider_event_at))
        .select_from(DeliveryEvent)
        .where(
            DeliveryEvent.organization_id == organization_id,
            DeliveryEvent.event_type == "Delivery",
        )
    )
    first_delivered = db.scalar(
        select(func.min(EmailMessage.delivered_at)).where(
            EmailMessage.organization_id == organization_id,
            EmailMessage.delivered_at.is_not(None),
        )
    )
    # Delivery events arrive before the message row is updated in a race, so take
    # whichever recorded the contact first rather than trusting one table.
    candidates = [value for value in (first_verified_contact, first_delivered) if value]
    first = min(candidates) if candidates else None
    return Activation(
        has_verified_domain=has_domain,
        has_api_key=has_key,
        has_sent_email=has_sent,
        first_delivered_at=first,
    )


def deliverability(
    db: Session, organization_id: UUID, *, days: int = 30, now: datetime | None = None
) -> Deliverability:
    """Rolling window counts plus the rates that decide whether sending continues."""
    since = (now or datetime.now(UTC)) - timedelta(days=days)
    rows = db.execute(
        select(DeliveryEvent.event_type, func.count())
        .where(
            DeliveryEvent.organization_id == organization_id,
            DeliveryEvent.received_at >= since,
        )
        .group_by(DeliveryEvent.event_type)
    ).all()
    by_type = {event_type: int(count) for event_type, count in rows}
    suppressed = _count(db, Suppression, Suppression.organization_id == organization_id)
    return Deliverability(
        sent=by_type.get("Send", 0),
        delivered=by_type.get("Delivery", 0),
        bounced=by_type.get("Bounce", 0),
        complained=by_type.get("Complaint", 0),
        suppressed=suppressed,
    )


@dataclass(frozen=True)
class DailyPoint:
    day: str
    emails: int


def volume_series(
    db: Session, organization_id: UUID, *, days: int = 14, today=None
) -> list[DailyPoint]:
    """Per-day sends for the sparkline, oldest first, missing days filled with zero.

    Zero-filled on purpose: a line chart with gaps drawn as gaps hides the most
    common failure, which is a sudden drop to nothing.
    """
    from app.models.quota import UsageDaily

    current = today or datetime.now(UTC).date()
    first = current - timedelta(days=days - 1)
    rows = db.execute(
        select(UsageDaily.usage_date, UsageDaily.emails_sent).where(
            UsageDaily.organization_id == organization_id,
            UsageDaily.usage_date >= first,
            UsageDaily.usage_date <= current,
        )
    ).all()
    counts = {str(day): int(count) for day, count in rows}
    return [
        DailyPoint(
            day=str(first + timedelta(days=offset)),
            emails=counts.get(str(first + timedelta(days=offset)), 0),
        )
        for offset in range(days)
    ]


@dataclass(frozen=True)
class Overview:
    organization_id: UUID
    plan: str
    activation: Activation
    daily: Usage
    monthly: MonthlyUsage
    daily_limit: int
    monthly_limit: int
    deliverability: Deliverability
    series: list[DailyPoint]


def overview(
    db: Session,
    organization: Organization,
    *,
    series_days: int = 14,
    deliverability_days: int = 30,
) -> Overview:
    """One round trip for the whole page.

    The limits are read here rather than passed in so the dashboard cannot show a
    stale ceiling if a plan is changed or an override is added.
    """
    from app.services.quota import load_limit

    limit = load_limit(db, organization)
    return Overview(
        organization_id=organization.id,
        plan=limit.plan,
        activation=activation(db, organization.id),
        daily=current_usage(db, organization.id),
        monthly=current_month_usage(db, organization.id),
        daily_limit=limit.daily_email_limit,
        monthly_limit=limit.monthly_email_limit,
        deliverability=deliverability(db, organization.id, days=deliverability_days),
        series=volume_series(db, organization.id, days=series_days),
    )
