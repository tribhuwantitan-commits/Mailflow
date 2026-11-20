"""Sending quota enforcement: daily email/recipient caps and per-recipient guard.

The check has to be atomic with the insert, otherwise two concurrent requests can
both see "one slot left" and both take it. So the accounting is a single locked
UPDATE on the (organization, UTC day) row, executed in the same transaction as the
email insert. If the reservation would exceed either cap, the update matches no
row, nothing is written, and the caller raises ``QuotaExceeded`` before the email
insert — no cleanup needed, no half-sent state.

Ordering matters: ``submit_email`` reserves first, then inserts. An idempotent
replay therefore never double-charges, because the replay is detected before the
reservation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.quota import RecipientDailyCount, SendingPlan, UsageDaily

#: Columns a tenant may override for itself via ``organizations.plan_overrides``.
OVERRIDABLE = (
    "daily_email_limit",
    "daily_recipient_limit",
    "monthly_email_limit",
    "monthly_recipient_limit",
    "max_recipients_per_email",
    "per_recipient_daily_limit",
)


@dataclass(frozen=True)
class EffectiveLimit:
    """The limits actually in force for one tenant today."""

    plan: str
    daily_email_limit: int
    daily_recipient_limit: int
    monthly_email_limit: int
    monthly_recipient_limit: int
    max_recipients_per_email: int
    per_recipient_daily_limit: int


@dataclass(frozen=True)
class Usage:
    emails_sent: int
    recipients_sent: int


@dataclass(frozen=True)
class MonthlyUsage:
    """Calendar-month totals, summed from the daily ledger.

    No separate monthly table: `usage_daily` already holds every send, so the sum is
    the source of truth and cannot drift from it. The index on (organization_id,
    usage_date) keeps this to a single short range scan.
    """

    emails_sent: int
    recipients_sent: int


class QuotaExceeded(Exception):
    """Raised when a send would cross a plan limit."""

    def __init__(self, code: str, message: str, headers: dict[str, str]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.headers = headers


class PlanMissing(Exception):
    """Raised when a tenant points at a plan slug that no longer exists."""


def utc_today() -> date:
    return datetime.now(UTC).date()


def recipient_digest(address: str) -> str:
    """Stable, non-reversible recipient key.

    Stored instead of the address so the guard table cannot be used to enumerate
    a tenant's recipients. Lowercased because the same mailbox is one mailbox.
    """
    return hashlib.sha256(address.strip().lower().encode()).hexdigest()


def effective_limit(organization: Organization, plan: SendingPlan) -> EffectiveLimit:
    """Merge the plan with a tenant's overrides; overrides win, plan is the floor."""
    overrides = organization.plan_overrides or {}
    values: dict[str, int] = {}
    for field in OVERRIDABLE:
        base = getattr(plan, field)
        override = overrides.get(field)
        values[field] = int(override) if isinstance(override, int) and override >= 0 else base
    return EffectiveLimit(plan=plan.slug, **values)


def load_limit(db: Session, organization: Organization) -> EffectiveLimit:
    plan = db.get(SendingPlan, organization.plan)
    if plan is None:
        raise PlanMissing(f"plan {organization.plan!r} is not defined")
    return effective_limit(organization, plan)


def current_usage(db: Session, organization_id: UUID, day: date | None = None) -> Usage:
    row = db.get(UsageDaily, {"organization_id": organization_id, "usage_date": day or utc_today()})
    if row is None:
        return Usage(emails_sent=0, recipients_sent=0)
    return Usage(emails_sent=row.emails_sent, recipients_sent=row.recipients_sent)


def month_bounds(day: date | None = None) -> tuple[date, date]:
    """First day of the month and the day after the last, for a half-open range."""
    current = day or utc_today()
    first = current.replace(day=1)
    following = (
        date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)
    )
    return first, following


def current_month_usage(
    db: Session, organization_id: UUID, day: date | None = None
) -> MonthlyUsage:
    first, following = month_bounds(day)
    emails, recipients = db.execute(
        select(
            func.coalesce(func.sum(UsageDaily.emails_sent), 0),
            func.coalesce(func.sum(UsageDaily.recipients_sent), 0),
        ).where(
            UsageDaily.organization_id == organization_id,
            UsageDaily.usage_date >= first,
            UsageDaily.usage_date < following,
        )
    ).one()
    return MonthlyUsage(emails_sent=int(emails), recipients_sent=int(recipients))


def _quota_headers(
    limit: EffectiveLimit, usage: Usage, monthly: MonthlyUsage | None = None
) -> dict[str, str]:
    headers = {
        "X-Quota-Plan": limit.plan,
        "X-Quota-Limit": str(limit.daily_email_limit),
        "X-Quota-Remaining": str(max(0, limit.daily_email_limit - usage.emails_sent)),
        "X-Quota-Monthly-Limit": str(limit.monthly_email_limit),
        "Retry-After": "3600",
    }
    if monthly is not None:
        headers["X-Quota-Monthly-Remaining"] = str(
            max(0, limit.monthly_email_limit - monthly.emails_sent)
        )
    return headers


def _ensure_row(db: Session, organization_id: UUID, day: date) -> None:
    """Create today's ledger row if absent.

    ``ON CONFLICT DO NOTHING`` takes a savepoint rather than aborting the outer
    transaction, so this is safe to call on every send including the very first
    one of the day.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    values = {"organization_id": organization_id, "usage_date": day}
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(pg_insert(UsageDaily).values(**values).on_conflict_do_nothing())
    elif dialect == "sqlite":
        db.execute(sqlite_insert(UsageDaily).values(**values).on_conflict_do_nothing())
    else:  # pragma: no cover - only PostgreSQL and SQLite are supported
        if db.get(UsageDaily, {**values}) is None:
            db.add(UsageDaily(**values))
            db.flush()


def reserve_send(
    db: Session,
    *,
    organization: Organization,
    recipients: list[str],
    limit: EffectiveLimit,
    day: date | None = None,
) -> Usage:
    """Atomically claim one email and ``len(recipients)`` recipient slots.

    Returns the usage *after* the reservation. Raises :class:`QuotaExceeded` when
    a cap would be crossed, having written nothing.
    """
    day = day or utc_today()
    recipient_count = len(recipients)

    if recipient_count > limit.max_recipients_per_email:
        raise QuotaExceeded(
            "too_many_recipients",
            f"At most {limit.max_recipients_per_email} recipients per email on this plan.",
            {
                "X-Quota-Plan": limit.plan,
                "X-Quota-Max-Recipients": str(limit.max_recipients_per_email),
            },
        )

    if limit.per_recipient_daily_limit:
        _guard_recipients(db, organization.id, recipients, limit, day)

    # Monthly first: it is the tighter of the two, and refusing here writes nothing.
    # The check is advisory (a concurrent send can slip past it), which is fine --
    # the daily UPDATE below stays the hard limit, so the overshoot is bounded by the
    # number of in-flight requests, not by the tenant's traffic.
    monthly = current_month_usage(db, organization.id, day)
    if monthly.emails_sent + 1 > limit.monthly_email_limit:
        raise QuotaExceeded(
            "monthly_email_quota_exceeded",
            f"Monthly limit of {limit.monthly_email_limit} emails reached for this plan.",
            _quota_headers(limit, current_usage(db, organization.id, day), monthly),
        )
    if monthly.recipients_sent + recipient_count > limit.monthly_recipient_limit:
        raise QuotaExceeded(
            "monthly_recipient_quota_exceeded",
            f"Monthly limit of {limit.monthly_recipient_limit} recipients reached for this plan.",
            _quota_headers(limit, current_usage(db, organization.id, day), monthly),
        )

    _ensure_row(db, organization.id, day)
    result = db.execute(
        update(UsageDaily)
        .where(
            UsageDaily.organization_id == organization.id,
            UsageDaily.usage_date == day,
            UsageDaily.emails_sent + 1 <= limit.daily_email_limit,
            UsageDaily.recipients_sent + recipient_count <= limit.daily_recipient_limit,
        )
        .values(
            emails_sent=UsageDaily.emails_sent + 1,
            recipients_sent=UsageDaily.recipients_sent + recipient_count,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        usage = current_usage(db, organization.id, day)
        headers = _quota_headers(limit, usage, current_month_usage(db, organization.id, day))
        if usage.emails_sent + 1 > limit.daily_email_limit:
            raise QuotaExceeded(
                "email_quota_exceeded",
                f"Daily limit of {limit.daily_email_limit} emails reached for this plan.",
                headers,
            )
        raise QuotaExceeded(
            "recipient_quota_exceeded",
            f"Daily limit of {limit.daily_recipient_limit} recipients reached for this plan.",
            headers,
        )

    return Usage(
        emails_sent=_scalar(db, organization.id, day, UsageDaily.emails_sent),
        recipients_sent=_scalar(db, organization.id, day, UsageDaily.recipients_sent),
    )


def _scalar(db: Session, organization_id: UUID, day: date, column) -> int:
    value = db.scalar(
        select(column).where(
            UsageDaily.organization_id == organization_id, UsageDaily.usage_date == day
        )
    )
    return int(value or 0)


def _guard_recipients(
    db: Session,
    organization_id: UUID,
    recipients: list[str],
    limit: EffectiveLimit,
    day: date,
) -> None:
    """Refuse a send that would exceed a single address's daily cap.

    Counts unique addresses once, so ``to: [a, a]`` costs one slot, matching what
    the transport actually does.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    unique: dict[str, str] = {}
    for address in recipients:
        unique.setdefault(recipient_digest(address), address)

    keys = [
        {"organization_id": organization_id, "recipient_hash": digest, "usage_date": day}
        for digest in unique
    ]
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(pg_insert(RecipientDailyCount).values(keys).on_conflict_do_nothing())
    elif dialect == "sqlite":
        db.execute(sqlite_insert(RecipientDailyCount).values(keys).on_conflict_do_nothing())
    else:  # pragma: no cover
        for key in keys:
            if db.get(RecipientDailyCount, key) is None:
                db.add(RecipientDailyCount(**key))
        db.flush()

    result = db.execute(
        update(RecipientDailyCount)
        .where(
            RecipientDailyCount.organization_id == organization_id,
            RecipientDailyCount.usage_date == day,
            RecipientDailyCount.recipient_hash.in_(list(unique)),
            RecipientDailyCount.count + 1 <= limit.per_recipient_daily_limit,
        )
        .values(count=RecipientDailyCount.count + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != len(unique):
        blocked = db.scalar(
            select(func.count())
            .select_from(RecipientDailyCount)
            .where(
                RecipientDailyCount.organization_id == organization_id,
                RecipientDailyCount.usage_date == day,
                RecipientDailyCount.recipient_hash.in_(list(unique)),
                RecipientDailyCount.count >= limit.per_recipient_daily_limit,
            )
        )
        raise QuotaExceeded(
            "recipient_daily_limit_exceeded",
            f"At most {limit.per_recipient_daily_limit} emails per recipient per day on this plan"
            f" ({blocked} address(es) already at the limit).",
            {
                "X-Quota-Plan": limit.plan,
                "X-Quota-Per-Recipient": str(limit.per_recipient_daily_limit),
            },
        )


def usage_summary(db: Session, organization: Organization) -> dict[str, object]:
    """Everything a dashboard needs about today's usage, in one round trip."""
    limit = load_limit(db, organization)
    usage = current_usage(db, organization.id)
    monthly = current_month_usage(db, organization.id)
    return {
        "plan": limit.plan,
        "limit": {
            "daily_emails": limit.daily_email_limit,
            "daily_recipients": limit.daily_recipient_limit,
            "monthly_emails": limit.monthly_email_limit,
            "monthly_recipients": limit.monthly_recipient_limit,
            "max_recipients_per_email": limit.max_recipients_per_email,
            "per_recipient_daily_limit": limit.per_recipient_daily_limit,
        },
        "used": {
            "emails": usage.emails_sent,
            "recipients": usage.recipients_sent,
            "monthly_emails": monthly.emails_sent,
            "monthly_recipients": monthly.recipients_sent,
        },
        "remaining": {
            "emails": max(0, limit.daily_email_limit - usage.emails_sent),
            "recipients": max(0, limit.daily_recipient_limit - usage.recipients_sent),
            "monthly_emails": max(0, limit.monthly_email_limit - monthly.emails_sent),
            "monthly_recipients": max(0, limit.monthly_recipient_limit - monthly.recipients_sent),
        },
        "resets_at": f"{utc_today()}T24:00:00Z",
        "monthly_resets_at": f"{month_bounds()[1].isoformat()}T00:00:00Z",
    }
