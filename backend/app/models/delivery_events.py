"""Delivery events, per-tenant suppressions and per-tenant reputation.

``delivery_events`` is an append-only audit trail fed by SES event publishing. It is
the tenant-scoped record of what actually happened to a message after SES accepted
it: delivered, bounced, complained, rejected, delayed. The SES console shows account
aggregates; this table is what a customer is allowed to see about their own mail.

``suppressions`` is the consequence of those events: once an address hard-bounces or
complains for a tenant, it is suppressed for that tenant and never contacted again.
Scoped per tenant on purpose — customer A suppressing ``user@x.com`` must not stop
customer B from mailing the same address legitimately.

``tenant_reputation`` is the rolling bounce/complaint rate per tenant, used to
auto-pause a tenant before AWS pauses the whole account for us. It is derived, not
authoritative; the event log is the source of truth.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#: Event types we ingest and expose. Anything else is stored as ``Unknown``.
EVENT_TYPES = (
    "Send",
    "Delivery",
    "Bounce",
    "Complaint",
    "Reject",
    "DeliveryDelay",
    "Open",
    "Click",
    "RenderingFailure",
)


class DeliveryEvent(Base):
    """One SES event about one message, tenant-scoped and append-only."""

    __tablename__ = "delivery_events"
    __table_args__ = (
        # SNS redelivers; this makes ingest idempotent without a lookup-first race.
        UniqueConstraint("provider_event_id", name="uq_delivery_events_provider_event"),
        Index("ix_delivery_events_email", "email_id", "provider_event_at"),
        Index("ix_delivery_events_org_received", "organization_id", "received_at"),
        Index("ix_delivery_events_provider_message", "provider_message_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    email_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("email_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: SNS `MessageId` — the dedupe key.
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    recipient: Mapped[str | None] = mapped_column(String(320))
    #: Raw event, so a bug in our parsing is recoverable without re-subscribing.
    payload: Mapped[str | None] = mapped_column(Text)
    provider_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Suppression(Base):
    """An address this tenant must never be sent to again."""

    __tablename__ = "suppressions"
    __table_args__ = (
        UniqueConstraint("organization_id", "recipient", name="uq_suppressions_org_recipient"),
        Index("ix_suppressions_org_reason", "organization_id", "reason"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Lowercased address, so lookups match what the transport does.
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    #: ``bounce`` (hard), ``complaint``, or ``manual``.
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TenantReputation(Base):
    """Per-tenant, per-day sending counts, for the auto-pause decision."""

    __tablename__ = "tenant_reputation"
    __table_args__ = (UniqueConstraint("organization_id", "day", name="uq_tenant_reputation_day"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    sent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    delivered: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    bounced: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    complained: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: Set once the tenant crosses a threshold; cleared by support after review.
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_reason: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
