"""Per-tenant sending domains.

A domain row is the platform's answer to "may this tenant send as this domain?".
The row is created in ``pending`` state, carries the DNS records SES generated,
and only becomes ``verified`` when SES says the identity is ``Success``. Sending
from an unverified domain is refused before the provider is called, so a tenant
can never borrow another tenant's reputation or ours.

Records are stored as JSON because they are provider output, not our schema: the
shape is whatever SES returns and may gain fields. Keeping them verbatim is also
what makes the setup UI a pure read.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATUSES = ("pending", "verified", "failed")


class Domain(Base):
    """A customer-owned domain registered for sending."""

    __tablename__ = "domains"
    __table_args__ = (
        UniqueConstraint("organization_id", "domain", name="uq_domains_org_domain"),
        UniqueConstraint("domain", name="uq_domains_global_domain"),
        CheckConstraint("status IN ('pending', 'verified', 'failed')", name="ck_domains_status"),
        CheckConstraint("domain = lower(domain)", name="ck_domains_lowercase"),
        Index("ix_domains_org_status", "organization_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Lowercased apex or subdomain, no trailing dot, no scheme.
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending", default="pending"
    )
    #: SES Easy DKIM CNAMEs, verbatim from the API, so the UI can show them.
    dkim_tokens: Mapped[list | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    #: Last verification attempt result, for the dashboard's "why is this failing".
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
