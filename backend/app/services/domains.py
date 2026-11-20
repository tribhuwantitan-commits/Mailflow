"""Domain registration, verification and the send-time ownership check.

Two rules, both enforced here rather than in the API layer:

1. A tenant can only send as a domain it has verified. The check reads the
   tenant's own rows, never a cached flag, so revoking a domain stops sending
   immediately rather than at the next cache expiry.
2. A domain belongs to exactly one tenant. Two tenants claiming the same apex
   would let one of them send as the other's brand, and SES identities are
   account-wide, so the second claim is refused at registration time.

Verification talks to SES through :class:`DomainVerifier`. The real adapter lives
in ``app.providers.ses_identities``; tests inject a stub, so none of this needs
AWS to run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.domain import Domain

#: Public mail providers a customer cannot verify, because they do not control
#: the DNS. Refused at registration with a message that says what to do instead.
UNVERIFIABLE_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "yahoo.co.in",
        "ymail.com",
        "aol.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "proton.me",
        "protonmail.com",
        "zoho.com",
        "mail.com",
        "gmx.com",
        "yandex.com",
        "rediffmail.com",
        "qq.com",
        "163.com",
        "126.com",
    }
)

#: ``localhost`` and bare hostnames are not sendable identities.
DOMAIN_PATTERN = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class DomainError(Exception):
    """A registration or verification problem with a customer-safe message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class IdentityState:
    """What SES thinks of one identity."""

    exists: bool
    verified: bool
    dkim_tokens: tuple[str, ...] = ()
    error: str | None = None


class DomainVerifier(Protocol):
    """The slice of SES identity management this module needs."""

    def register(self, domain: str) -> IdentityState:
        """Create the identity if absent and return its DKIM tokens."""
        ...

    def check(self, domain: str) -> IdentityState:
        """Read the current verification state without creating anything."""
        ...

    def remove(self, domain: str) -> None:
        """Delete the identity; best effort, used when a tenant deletes a domain."""
        ...


def normalize(raw: str) -> str:
    """Lowercase, strip a scheme, a path, a trailing dot and a leading ``www.``."""
    value = raw.strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/", 1)[0]
    value = value.rstrip(".")
    if value.startswith("www."):
        value = value[4:]
    return value


def validate(raw: str) -> str:
    value = normalize(raw)
    if not value:
        raise DomainError("domain_invalid", "A domain is required.")
    if "@" in value:
        raise DomainError(
            "domain_invalid",
            "Enter the domain only, without the part before the @ "
            "(example: acme.com, not you@acme.com).",
        )
    if value in UNVERIFIABLE_DOMAINS:
        raise DomainError(
            "domain_not_verifiable",
            f"{value} is a public mail provider, so its DNS cannot be verified. "
            "Verify a domain you own and send from that instead.",
        )
    if not DOMAIN_PATTERN.match(value):
        raise DomainError(
            "domain_invalid",
            "That does not look like a domain. Use a form like acme.com.",
        )
    return value


def domain_of_address(address: str) -> str:
    return address.rsplit("@", 1)[-1].strip().lower() if "@" in address else ""


def list_for_org(db: Session, organization_id: UUID) -> list[Domain]:
    return list(
        db.scalars(
            select(Domain)
            .where(Domain.organization_id == organization_id)
            .order_by(Domain.created_at, Domain.id)
        ).all()
    )


def get_verified(db: Session, organization_id: UUID, domain: str) -> Domain | None:
    return db.scalar(
        select(Domain).where(
            Domain.organization_id == organization_id,
            Domain.domain == domain,
            Domain.status == "verified",
        )
    )


def register(
    db: Session,
    *,
    organization_id: UUID,
    raw_domain: str,
    verifier: DomainVerifier,
) -> Domain:
    """Create the tenant's domain row and the matching SES identity.

    The row is written first in ``pending`` state so a crash between the two
    calls leaves a visible pending domain rather than an orphan SES identity the
    tenant cannot see. A duplicate claim is refused before SES is touched.
    """
    domain = validate(raw_domain)

    taken = db.scalar(select(Domain).where(Domain.domain == domain))
    if taken is not None:
        if taken.organization_id != organization_id:
            raise DomainError(
                "domain_taken",
                "That domain is already registered on this platform. "
                "If it is yours, contact support.",
            )
        raise DomainError("domain_exists", "That domain is already added to this organization.")

    state = verifier.register(domain)
    row = Domain(
        organization_id=organization_id,
        domain=domain,
        status="verified" if state.verified else "pending",
        dkim_tokens=list(state.dkim_tokens) or None,
        last_checked_at=datetime.now(UTC),
        last_error=state.error,
        verified_at=datetime.now(UTC) if state.verified else None,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        # Lost a race against a concurrent claim; the unique constraints did their job.
        db.rollback()
        raise DomainError(
            "domain_taken",
            "That domain is already registered on this platform.",
        ) from None
    return row


def refresh(db: Session, *, row: Domain, verifier: DomainVerifier) -> Domain:
    """Re-read SES state for one domain and persist it."""
    state = verifier.check(row.domain)
    row.last_checked_at = datetime.now(UTC)
    row.last_error = state.error
    if state.dkim_tokens:
        row.dkim_tokens = list(state.dkim_tokens)
    if state.verified:
        row.status = "verified"
        row.verified_at = row.verified_at or datetime.now(UTC)
    elif not state.exists:
        row.status = "failed"
    else:
        row.status = "pending"
    db.flush()
    return row


def delete(db: Session, *, row: Domain, verifier: DomainVerifier) -> None:
    """Remove the row, then the SES identity.

    Identity removal is best effort: failing to delete it must not block the
    tenant from removing the domain from their account, and the orphan identity
    is harmless because no row points at it.
    """
    db.delete(row)
    db.flush()
    try:
        verifier.remove(row.domain)
    except Exception:  # pragma: no cover - provider best effort
        pass


def sender_domain_allowed(db: Session, organization_id: UUID, sender: str) -> bool:
    """True when ``sender``'s domain is a verified domain of this tenant."""
    domain = domain_of_address(sender)
    if not domain:
        return False
    return get_verified(db, organization_id, domain) is not None
