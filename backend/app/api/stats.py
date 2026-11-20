"""Dashboard summary: activation, quota consumption, deliverability.

Session-authenticated, not API-key authenticated, because this is what the customer
sees in the browser. Every query is scoped to an organization the caller provably
belongs to -- the membership check runs before any stat is read.
"""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db_session
from app.api.domains import membership
from app.api.errors import APIError
from app.models import Organization, User
from app.services import stats

router = APIRouter()


class StepRead(BaseModel):
    key: str
    label: str
    done: bool


class ActivationRead(BaseModel):
    complete: bool
    first_delivered_at: datetime | None
    steps: list[StepRead]


class DeliverabilityRead(BaseModel):
    sent: int
    delivered: int
    bounced: int
    complained: int
    suppressed: int
    bounce_rate: float
    complaint_rate: float
    judged: int
    window_days: int


class LimitRead(BaseModel):
    daily_emails: int
    monthly_emails: int


class UsedRead(BaseModel):
    daily_emails: int
    monthly_emails: int


class RemainingRead(BaseModel):
    daily_emails: int
    monthly_emails: int


class VolumePointRead(BaseModel):
    day: str
    emails: int


class OverviewRead(BaseModel):
    organization_id: UUID
    plan: str
    activation: ActivationRead
    limit: LimitRead
    used: UsedRead
    remaining: RemainingRead
    deliverability: DeliverabilityRead
    volume: list[VolumePointRead]


def _unavailable() -> APIError:
    return APIError(
        status_code=503,
        code="stats_unavailable",
        message="Statistics are temporarily unavailable.",
    )


@router.get("/{organization_id}/stats", response_model=OverviewRead)
def organization_stats(
    organization_id: UUID,
    response: Response,
    window_days: int = Query(default=30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> OverviewRead:
    """Everything the dashboard renders, in one request."""
    membership(db, organization_id, current_user, owner_only=False)
    organization = db.get(Organization, organization_id)
    if organization is None:  # pragma: no cover - membership row implies the org
        raise APIError(
            status_code=404, code="organization_not_found", message="Organization not found."
        )

    try:
        data = stats.overview(db, organization, deliverability_days=window_days)
    except SQLAlchemyError:
        raise _unavailable() from None

    # Counters must never be served from a cache: a customer watching quota tick up
    # after an upgrade would conclude the upgrade did not work.
    response.headers["Cache-Control"] = "no-store"
    return OverviewRead(
        organization_id=data.organization_id,
        plan=data.plan,
        activation=ActivationRead(
            complete=data.activation.complete,
            first_delivered_at=data.activation.first_delivered_at,
            steps=[StepRead(**step) for step in data.activation.as_steps()],
        ),
        limit=LimitRead(daily_emails=data.daily_limit, monthly_emails=data.monthly_limit),
        used=UsedRead(
            daily_emails=data.daily.emails_sent,
            monthly_emails=data.monthly.emails_sent,
        ),
        remaining=RemainingRead(
            daily_emails=max(0, data.daily_limit - data.daily.emails_sent),
            monthly_emails=max(0, data.monthly_limit - data.monthly.emails_sent),
        ),
        deliverability=DeliverabilityRead(
            sent=data.deliverability.sent,
            delivered=data.deliverability.delivered,
            bounced=data.deliverability.bounced,
            complained=data.deliverability.complained,
            suppressed=data.deliverability.suppressed,
            bounce_rate=round(data.deliverability.bounce_rate, 4),
            complaint_rate=round(data.deliverability.complaint_rate, 4),
            judged=data.deliverability.judged,
            window_days=window_days,
        ),
        volume=[VolumePointRead(day=point.day, emails=point.emails) for point in data.series],
    )


@router.get("/{organization_id}/emails", response_model=list[dict])
def recent_emails(
    organization_id: UUID,
    response: Response,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[dict]:
    """The activity table: newest first, tenant-scoped, bodies omitted.

    Bodies are left out on purpose. They are the expensive part of the row, the list
    does not display them, and after 30 days they are gone anyway -- so a summary
    that never carried them cannot break when retention runs.
    """
    from sqlalchemy import select

    from app.models.delivery import EmailMessage

    membership(db, organization_id, current_user, owner_only=False)
    try:
        rows = db.scalars(
            select(EmailMessage)
            .where(EmailMessage.organization_id == organization_id)
            .order_by(EmailMessage.created_at.desc())
            .limit(limit)
        ).all()
    except SQLAlchemyError:
        raise _unavailable() from None

    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "id": str(row.id),
            "from": row.sender,
            "to": json.loads(row.recipients),
            "subject": row.subject,
            "status": row.status,
            "error_code": row.error_code,
            "created_at": row.created_at.isoformat(),
            "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
            "bounced_at": row.bounced_at.isoformat() if row.bounced_at else None,
        }
        for row in rows
    ]
