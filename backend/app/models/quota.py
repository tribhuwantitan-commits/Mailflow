"""Per-tenant sending plan and the rolling daily usage ledger.

Two tables, two jobs:

``sending_plans`` is the catalogue — what a plan allows. ``organizations.plan``
is the slug a tenant is on, and ``organizations.plan_overrides`` lets support
grant a bigger limit to one tenant without inventing a plan for them.

``usage_daily`` is the ledger. One row per (organization, UTC day) holding the
email and recipient counts already consumed. It is written inside the same
transaction as the email insert, under a row lock, so two concurrent requests
can never both slip past the last slot of a quota. A day row costs a few dozen
bytes; the alternative (counting ``email_messages`` on every send) turns each
send into a table scan and makes the cost grow with history rather than with
the request.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#: Launch catalogue, single source of truth for the migration and for test seeding.
#: slug, name, daily emails, daily recipients, max per email, per-recipient cap, cents
DEFAULT_PLANS: tuple[dict[str, object], ...] = (
    {
        "slug": "free",
        "name": "Free",
        "daily_email_limit": 50,
        "daily_recipient_limit": 50,
        "max_recipients_per_email": 5,
        "per_recipient_daily_limit": 10,
        "price_cents_usd": 0,
    },
    {
        "slug": "free_card",
        "name": "Free (card verified)",
        "daily_email_limit": 100,
        "daily_recipient_limit": 100,
        "max_recipients_per_email": 10,
        # 0 means "no cap" to the guard, which let one address take all 100 sends.
        "per_recipient_daily_limit": 10,
        "price_cents_usd": 0,
    },
    {
        # Daily limit x 30 stays under what the price can pay for: at $0.10 per 1,000
        # an email costs $0.003 of a month's revenue, so 1,000/day ($9) spends ~33%.
        # The old limits allowed 1.2M emails a month on the $15 plan.
        "slug": "starter",
        "name": "Starter",
        "daily_email_limit": 1_000,
        "daily_recipient_limit": 1_000,
        "max_recipients_per_email": 50,
        "per_recipient_daily_limit": 0,
        "price_cents_usd": 900,
    },
    {
        "slug": "growth",
        "name": "Growth",
        "daily_email_limit": 2_500,
        "daily_recipient_limit": 2_500,
        "max_recipients_per_email": 50,
        "per_recipient_daily_limit": 0,
        "price_cents_usd": 1_900,
    },
    {
        "slug": "scale",
        "name": "Scale",
        "daily_email_limit": 5_800,
        "daily_recipient_limit": 5_800,
        "max_recipients_per_email": 50,
        "per_recipient_daily_limit": 0,
        "price_cents_usd": 3_900,
    },
    {
        "slug": "business",
        "name": "Business",
        "daily_email_limit": 13_000,
        "daily_recipient_limit": 13_000,
        "max_recipients_per_email": 50,
        "per_recipient_daily_limit": 0,
        "price_cents_usd": 7_900,
    },
)


class SendingPlan(Base):
    """A sellable tier: daily quota, per-recipient guard rails, price."""

    __tablename__ = "sending_plans"
    __table_args__ = (
        CheckConstraint("daily_email_limit > 0", name="ck_sending_plans_daily_limit"),
        CheckConstraint("daily_recipient_limit > 0", name="ck_sending_plans_recipient_limit"),
        CheckConstraint("max_recipients_per_email > 0", name="ck_sending_plans_per_email"),
        CheckConstraint("per_recipient_daily_limit >= 0", name="ck_sending_plans_per_recipient"),
        CheckConstraint("price_cents_usd >= 0", name="ck_sending_plans_price"),
    )

    slug: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    daily_email_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_recipient_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    max_recipients_per_email: Mapped[int] = mapped_column(Integer, nullable=False)
    # 0 disables the per-recipient guard (paid plans); free plans keep it on so a
    # single address cannot be OTP-bombed through us.
    per_recipient_daily_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    price_cents_usd: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true", default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UsageDaily(Base):
    """Emails and recipients already accepted for one tenant on one UTC day."""

    __tablename__ = "usage_daily"
    __table_args__ = (
        CheckConstraint("emails_sent >= 0", name="ck_usage_daily_emails"),
        CheckConstraint("recipients_sent >= 0", name="ck_usage_daily_recipients"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    usage_date: Mapped[date] = mapped_column(Date, primary_key=True)
    emails_sent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    recipients_sent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RecipientDailyCount(Base):
    """Per-recipient counter used to stop OTP bombing of a single address."""

    __tablename__ = "recipient_daily_counts"
    __table_args__ = (CheckConstraint("count >= 0", name="ck_recipient_daily_counts_count"),)

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    recipient_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    usage_date: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
