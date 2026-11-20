"""Tenant-scoped email submission and status views."""

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.api.email_auth import get_email_key
from app.api.errors import APIError
from app.models.delivery import APIKey, EmailMessage, OutboxEvent
from app.models.organization import Organization
from app.services.domains import sender_domain_allowed
from app.services.quota import (
    PlanMissing,
    QuotaExceeded,
    load_limit,
    reserve_send,
    usage_summary,
)

router = APIRouter()


class EmailCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender: EmailStr = Field(alias="from")
    to: list[EmailStr] = Field(min_length=1, max_length=50)
    subject: str = Field(min_length=1, max_length=998)
    text_body: str | None = Field(default=None, max_length=100_000)
    html_body: str | None = Field(default=None, max_length=100_000)
    reply_to: EmailStr | None = None

    @model_validator(mode="after")
    def validate_content(self):
        if not self.text_body and not self.html_body:
            raise ValueError("At least one nonempty body is required")
        if len(self.model_dump_json()) > 200_000:
            raise ValueError("Email request is too large")
        return self


def view(message: EmailMessage) -> dict:
    return {
        "id": message.id,
        "organization_id": message.organization_id,
        "from": message.sender,
        "to": json.loads(message.recipients),
        "subject": message.subject,
        "text_body": message.text_body,
        "html_body": message.html_body,
        "reply_to": message.reply_to,
        "status": message.status,
        "provider": message.provider,
        "provider_message_id": message.provider_message_id,
        "attempt_count": message.attempt_count,
        "error_code": message.error_code,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
    }


def unavailable() -> APIError:
    return APIError(
        status_code=503,
        code="email_service_unavailable",
        message="Email service is temporarily unavailable.",
    )


def conflict() -> APIError:
    return APIError(
        status_code=409,
        code="idempotency_conflict",
        message="Idempotency key used with different content.",
    )


def quota_error(exc: QuotaExceeded) -> APIError:
    """Translate a quota refusal into the API's uniform error envelope."""
    return APIError(status_code=429, code=exc.code, message=exc.message, headers=exc.headers)


def plan_error() -> APIError:
    return APIError(
        status_code=503,
        code="plan_not_configured",
        message="This organization's sending plan is not configured.",
    )


def sender_not_verified(sender: str) -> APIError:
    """Refuse a send whose From domain this tenant has not verified."""
    domain = sender.rsplit("@", 1)[-1].lower() if "@" in sender else sender
    return APIError(
        status_code=403,
        code="sender_domain_not_verified",
        message=(
            f"The domain {domain} is not verified for this organization. "
            "Add and verify it under Sending domains before sending from it."
        ),
    )


def existing(db: Session, key: APIKey, idempotency: str) -> EmailMessage | None:
    return db.scalar(
        select(EmailMessage).where(
            EmailMessage.organization_id == key.organization_id,
            EmailMessage.idempotency_key == idempotency,
        )
    )


@router.post("", status_code=202)
def submit_email(
    payload: EmailCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, min_length=1, max_length=128),
    key: APIKey = Depends(get_email_key),
    db: Session = Depends(get_db_session),
) -> dict:
    normalized = payload.model_dump(mode="json", by_alias=True)
    digest = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    try:
        previous = existing(db, key, idempotency_key) if idempotency_key else None
        if previous:
            if previous.request_hash != digest:
                raise conflict()
            response.headers["Cache-Control"] = "no-store"
            return view(previous)

        # A tenant may only send as a domain it has verified. Checked before quota
        # so a refusal never consumes the tenant's daily allowance.
        if not sender_domain_allowed(db, key.organization_id, str(payload.sender)):
            raise sender_not_verified(str(payload.sender))

        # Reserve quota before insert so an idempotent replay never double-charges,
        # and a refusal writes nothing at all. The reservation and the email insert
        # share one transaction: either both land or neither does.
        organization = db.get(Organization, key.organization_id)
        if organization is None:
            raise plan_error()
        try:
            limit = load_limit(db, organization)
        except PlanMissing:
            raise plan_error() from None
        try:
            used = reserve_send(
                db,
                organization=organization,
                recipients=[str(item) for item in payload.to],
                limit=limit,
            )
        except QuotaExceeded as exc:
            db.rollback()
            raise quota_error(exc) from None

        message = EmailMessage(
            organization_id=key.organization_id,
            api_key_id=key.id,
            idempotency_key=idempotency_key,
            request_hash=digest,
            sender=str(payload.sender),
            recipients=json.dumps([str(item) for item in payload.to]),
            subject=payload.subject,
            text_body=payload.text_body,
            html_body=payload.html_body,
            reply_to=str(payload.reply_to) if payload.reply_to else None,
            status="accepted",
            attempt_count=0,
        )
        db.add(message)
        db.flush()
        db.add(OutboxEvent(email_id=message.id, state="pending"))
        db.commit()
        db.refresh(message)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Quota-Remaining"] = str(
            max(0, limit.daily_email_limit - used.emails_sent)
        )
        return view(message)
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            try:
                previous = existing(db, key, idempotency_key)
                if previous:
                    if previous.request_hash != digest:
                        raise conflict()
                    return view(previous)
            except SQLAlchemyError:
                raise unavailable() from None
        raise unavailable() from None
    except SQLAlchemyError:
        db.rollback()
        raise unavailable() from None


@router.get("")
def list_emails(
    response: Response,
    key: APIKey = Depends(get_email_key),
    db: Session = Depends(get_db_session),
) -> list[dict]:
    try:
        messages = db.scalars(
            select(EmailMessage)
            .where(EmailMessage.organization_id == key.organization_id)
            .order_by(EmailMessage.created_at.desc(), EmailMessage.id.desc())
            .limit(100)
        ).all()
        response.headers["Cache-Control"] = "no-store"
        return [view(message) for message in messages]
    except SQLAlchemyError:
        raise unavailable() from None


@router.get("/usage", response_model=None)
def get_usage(
    response: Response,
    key: APIKey = Depends(get_email_key),
    db: Session = Depends(get_db_session),
) -> dict:
    """Today's quota consumption and the limits that apply to this organization."""
    try:
        organization = db.get(Organization, key.organization_id)
        if organization is None:
            raise plan_error()
        try:
            summary = usage_summary(db, organization)
        except PlanMissing:
            raise plan_error() from None
    except SQLAlchemyError:
        raise unavailable() from None
    response.headers["Cache-Control"] = "no-store"
    return summary


@router.get("/{email_id}")
def get_email(
    email_id: UUID,
    response: Response,
    key: APIKey = Depends(get_email_key),
    db: Session = Depends(get_db_session),
) -> dict:
    try:
        message = db.scalar(
            select(EmailMessage).where(
                EmailMessage.id == email_id, EmailMessage.organization_id == key.organization_id
            )
        )
    except SQLAlchemyError:
        raise unavailable() from None
    if message is None:
        raise APIError(status_code=404, code="email_not_found", message="Email not found.")
    response.headers["Cache-Control"] = "no-store"
    return view(message)
