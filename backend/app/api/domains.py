"""Sending-domain management for the account dashboard.

Registering a domain is the first thing a customer does after signing up, and it
is also the gate that stops them sending. So the failures here are written for a
customer, not for a log: "gmail.com cannot be verified" rather than a 400.

Routes are owner-only for writes and member-visible for reads — a member needs to
see why sending is refused, but should not be able to attach a new domain to the
organization's reputation.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db_session
from app.api.errors import APIError
from app.models import OrganizationMembership, User
from app.models.domain import Domain
from app.services.domains import (
    DomainError,
    list_for_org,
    refresh,
    register,
)
from app.services.domains import (
    delete as delete_domain,
)

router = APIRouter()


class DomainCreate(BaseModel):
    domain: str = Field(min_length=3, max_length=253)


class DnsRecord(BaseModel):
    """One record the customer must publish, in the shape every DNS UI accepts."""

    type: Literal["CNAME", "TXT"]
    name: str
    value: str


class DomainRead(BaseModel):
    id: UUID
    organization_id: UUID
    domain: str
    status: Literal["pending", "verified", "failed"]
    dns_records: list[DnsRecord]
    last_checked_at: datetime | None
    last_error: str | None
    verified_at: datetime | None
    created_at: datetime


def membership(db: Session, organization_id: UUID, user: User, *, owner_only: bool) -> str:
    """Return the caller's role, or 404 as if the organization did not exist."""
    row = db.get(OrganizationMembership, (organization_id, user.id))
    if row is None or (owner_only and row.role != "owner"):
        raise APIError(
            status_code=404, code="organization_not_found", message="Organization not found."
        )
    return row.role


def unavailable() -> APIError:
    return APIError(
        status_code=503,
        code="domain_service_unavailable",
        message="Domain service is temporarily unavailable.",
    )


def domain_error(exc: DomainError) -> APIError:
    """Map a domain failure onto a status a client can branch on."""
    status = {
        "domain_taken": 409,
        "domain_exists": 409,
        "domain_invalid": 400,
        "domain_not_verifiable": 400,
        "provider_limit": 503,
        "provider_unavailable": 503,
    }.get(exc.code, 502)
    return APIError(status_code=status, code=exc.code, message=exc.message)


def dns_records(domain: Domain) -> list[DnsRecord]:
    """Render the three Easy DKIM CNAMEs SES generated for this domain."""
    tokens = domain.dkim_tokens or []
    return [
        DnsRecord(
            type="CNAME",
            name=f"{token}._domainkey.{domain.domain}",
            value=f"{token}.dkim.amazonses.com",
        )
        for token in tokens
    ]


def view(domain: Domain) -> DomainRead:
    return DomainRead(
        id=domain.id,
        organization_id=domain.organization_id,
        domain=domain.domain,
        status=domain.status,
        dns_records=dns_records(domain),
        last_checked_at=domain.last_checked_at,
        last_error=domain.last_error,
        verified_at=domain.verified_at,
        created_at=domain.created_at,
    )


def verifier(request: Request):
    return request.app.state.domain_verifier


@router.get("", response_model=list[DomainRead])
def list_domains(
    organization_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[DomainRead]:
    try:
        membership(db, organization_id, user, owner_only=False)
        rows = list_for_org(db, organization_id)
    except SQLAlchemyError:
        raise unavailable() from None
    response.headers["Cache-Control"] = "no-store"
    return [view(row) for row in rows]


@router.post("", response_model=DomainRead, status_code=201)
def create_domain(
    organization_id: UUID,
    payload: DomainCreate,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> DomainRead:
    try:
        membership(db, organization_id, user, owner_only=True)
        try:
            row = register(
                db,
                organization_id=organization_id,
                raw_domain=payload.domain,
                verifier=verifier(request),
            )
        except DomainError as exc:
            db.rollback()
            raise domain_error(exc) from None
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        raise unavailable() from None
    response.headers["Cache-Control"] = "no-store"
    return view(row)


@router.post("/{domain_id}/check", response_model=DomainRead)
def check_domain(
    organization_id: UUID,
    domain_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> DomainRead:
    """Re-read SES verification state; the customer calls this after publishing DNS."""
    try:
        membership(db, organization_id, user, owner_only=False)
        row = owned(db, organization_id, domain_id)
        try:
            refresh(db, row=row, verifier=verifier(request))
        except DomainError as exc:
            db.rollback()
            raise domain_error(exc) from None
        db.commit()
        db.refresh(row)
    except SQLAlchemyError:
        db.rollback()
        raise unavailable() from None
    response.headers["Cache-Control"] = "no-store"
    return view(row)


@router.delete("/{domain_id}", status_code=204)
def remove_domain(
    organization_id: UUID,
    domain_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Response:
    try:
        membership(db, organization_id, user, owner_only=True)
        row = owned(db, organization_id, domain_id)
        delete_domain(db, row=row, verifier=verifier(request))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise unavailable() from None
    return Response(status_code=204)


def owned(db: Session, organization_id: UUID, domain_id: UUID) -> Domain:
    row = db.get(Domain, domain_id)
    if row is None or row.organization_id != organization_id:
        raise APIError(status_code=404, code="domain_not_found", message="Domain not found.")
    return row
