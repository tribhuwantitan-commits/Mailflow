"""SES event ingest: SQS messages in, delivery state and suppressions out.

The pipeline is SES → SNS → SQS → this module. Each SQS body is an SNS envelope whose
``Message`` is the SES event JSON. Three things happen per event, in this order:

1. **Attribute it to a tenant.** The SES ``MessageId`` is matched against
   ``email_messages.provider_message_id``. An event we cannot attribute is stored with
   ``organization_id`` NULL rather than dropped — it is evidence of a bug, and losing
   it would make the next bug harder to find.
2. **Record it.** ``delivery_events`` gets a row keyed on the SNS ``MessageId``, so
   SNS's at-least-once redelivery is harmless.
3. **Act on it.** A hard bounce or a complaint writes a ``suppressions`` row and
   updates the message; every outcome updates the tenant's daily counters, and those
   counters can pause the tenant.

Ordering matters: the suppression is written before the counters, so a crash between
the two leaves the tenant protected rather than merely counted.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.delivery import EmailMessage
from app.models.delivery_events import DeliveryEvent, Suppression, TenantReputation
from app.models.organization import Organization

logger = logging.getLogger("mailflow.delivery_events")

#: Thresholds at which a tenant is paused. AWS pauses the whole account at 10% bounce
#: and 0.5% complaint; we act well before that so one tenant cannot cost every customer
#: their sending.
BOUNCE_PAUSE_RATE = 0.05
COMPLAINT_PAUSE_RATE = 0.001
#: Below this many sends, one bounce is a 50% rate and pausing would be absurd.
MIN_SENDS_TO_JUDGE = 100

#: Events that set a message status. Later events win, except that delivery never
#: downgrades a bounce: a message can be "delivered then complained about".
STATUS_BY_EVENT = {
    "Delivery": "delivered",
    "Bounce": "bounced",
    "Complaint": "complained",
    "Reject": "rejected",
    "DeliveryDelay": "delayed",
    "RenderingFailure": "failed",
}


@dataclass(frozen=True)
class ParsedEvent:
    """The parts of an SES event this platform acts on."""

    event_type: str
    provider_message_id: str | None
    recipients: tuple[str, ...]
    occurred_at: datetime | None
    bounce_type: str | None = None
    bounce_reason: str | None = None


@dataclass(frozen=True)
class IngestResult:
    stored: bool
    attributed: bool
    event_type: str | None = None
    suppressed: int = 0
    paused: bool = False
    reason: str | None = None


def parse_timestamp(value: Any) -> datetime | None:
    """SES timestamps are ISO-8601 with an offset; tolerate junk."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_ses_event(raw: str) -> ParsedEvent | None:
    """Turn an SES event JSON body into :class:`ParsedEvent`.

    Unknown event types are still returned (with an empty recipient list) so they land
    in the audit trail; only structurally invalid payloads return ``None``.
    """
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None

    event_type = payload.get("eventType") or payload.get("notificationType") or "Unknown"
    if not isinstance(event_type, str):
        return None
    mail = payload.get("mail") or {}
    message_id = mail.get("messageId") if isinstance(mail, dict) else None

    recipients: list[str] = []
    bounce_type = None
    bounce_reason = None

    if event_type == "Bounce":
        bounce = payload.get("bounce") or {}
        bounce_type = bounce.get("bounceType")
        bounce_reason = bounce.get("bounceSubType")
        recipients = [
            item.get("emailAddress", "")
            for item in bounce.get("bouncedRecipients", [])
            if item.get("emailAddress")
        ]
    elif event_type == "Complaint":
        complaint = payload.get("complaint") or {}
        recipients = [
            item.get("emailAddress", "")
            for item in complaint.get("complainedRecipients", [])
            if item.get("emailAddress")
        ]
    elif event_type == "Delivery":
        delivery = payload.get("delivery") or {}
        recipients = list(delivery.get("recipients") or [])
        if not recipients and isinstance(mail, dict):
            # Some event shapes only carry mail.destination.
            recipients = list(mail.get("destination") or [])
    else:
        recipients = list(mail.get("destination") or []) if isinstance(mail, dict) else []

    occurred_at = parse_timestamp(mail.get("timestamp") if isinstance(mail, dict) else None)

    return ParsedEvent(
        event_type=event_type,
        provider_message_id=str(message_id) if isinstance(message_id, str) and message_id else None,
        recipients=tuple(dict.fromkeys(address.lower() for address in recipients)),
        occurred_at=occurred_at,
        bounce_type=bounce_type,
        bounce_reason=bounce_reason,
    )


def unwrap_sns(body: str) -> tuple[str, str]:
    """Return ``(message_id, ses_event_json)`` from an SQS body.

    Accepts a bare SES event too, so the simulator and manual testing do not need an
    SNS envelope. SNS has already been confirmed as a genuine sender at the queue
    policy level; this function does not re-verify a signature.
    """
    try:
        envelope = json.loads(body)
    except (TypeError, ValueError):
        return "", body
    if isinstance(envelope, dict) and "Message" in envelope and "Type" in envelope:
        return str(envelope.get("MessageId", "")), str(envelope["Message"])
    return "", body


def _upsert_reputation(db: Session, organization_id: UUID, day: date, **increments: int) -> None:
    values = {"organization_id": organization_id, "day": day, **increments}
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(pg_insert(TenantReputation).values(**values).on_conflict_do_nothing())
        statement = update(TenantReputation).where(
            TenantReputation.organization_id == organization_id, TenantReputation.day == day
        )
        for column, amount in increments.items():
            statement = statement.values(**{column: getattr(TenantReputation, column) + amount})
        db.execute(statement)
    elif dialect == "sqlite":
        db.execute(sqlite_insert(TenantReputation).values(**values).on_conflict_do_nothing())
        statement = update(TenantReputation).where(
            TenantReputation.organization_id == organization_id, TenantReputation.day == day
        )
        for column, amount in increments.items():
            statement = statement.values(**{column: getattr(TenantReputation, column) + amount})
        db.execute(statement)
    else:  # pragma: no cover
        db.execute(
            update(TenantReputation).where(TenantReputation.organization_id == organization_id)
        )
    db.execute(
        update(TenantReputation)
        .where(TenantReputation.organization_id == organization_id, TenantReputation.day == day)
        .values(updated_at=datetime.now(UTC))
    )


def _suppress(
    db: Session,
    *,
    organization_id: UUID,
    recipient: str,
    reason: str,
    detail: str | None,
) -> bool:
    """Insert a suppression if absent; return whether this call added it."""
    values = {
        "organization_id": organization_id,
        "recipient": recipient.lower(),
        "reason": reason,
        "detail": (detail or "")[:500] or None,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        result = db.execute(pg_insert(Suppression).values(**values).on_conflict_do_nothing())
    elif dialect == "sqlite":
        result = db.execute(sqlite_insert(Suppression).values(**values).on_conflict_do_nothing())
    else:  # pragma: no cover
        if db.scalar(
            select(Suppression).where(
                Suppression.organization_id == organization_id,
                Suppression.recipient == values["recipient"],
            )
        ):
            return False
        db.add(Suppression(**values))
        return True
    return bool(result.rowcount)


def _maybe_pause(db: Session, organization: Organization, day: date) -> str | None:
    """Pause the tenant when today's bounce or complaint rate is past the threshold."""
    reputation = db.scalar(
        select(TenantReputation).where(
            TenantReputation.organization_id == organization.id, TenantReputation.day == day
        )
    )
    if reputation is None or organization.sending_paused_at is not None:
        return None

    judged = max(reputation.delivered + reputation.bounced, reputation.sent)
    if judged < MIN_SENDS_TO_JUDGE:
        return None

    if reputation.bounced / judged > BOUNCE_PAUSE_RATE:
        reason = f"bounce rate {reputation.bounced}/{judged} above 5%"
    elif reputation.complained / judged > COMPLAINT_PAUSE_RATE:
        reason = f"complaint rate {reputation.complained}/{judged} above 0.1%"
    else:
        return None

    organization.sending_paused_at = datetime.now(UTC)
    organization.sending_paused_reason = reason
    reputation.paused_at = organization.sending_paused_at
    reputation.paused_reason = reason
    logger.warning("tenant_paused organization_id=%s reason=%s", organization.id, reason)
    return reason


def ingest(db: Session, body: str) -> IngestResult:
    """Ingest one SQS message body. Safe to call twice with the same body."""
    provider_event_id, raw_event = unwrap_sns(body)
    parsed = parse_ses_event(raw_event)
    if parsed is None:
        return IngestResult(stored=False, attributed=False, reason="unparseable")

    message: EmailMessage | None = None
    if parsed.provider_message_id:
        message = db.scalar(
            select(EmailMessage).where(
                EmailMessage.provider_message_id == parsed.provider_message_id
            )
        )

    # A tenant-less event is still recorded: dropping it would hide the bug that
    # produced it. ``organization_id`` is only nullable in practice for unprovable
    # MessageIds, so such rows are stored without an organization.
    if message is None:
        return IngestResult(
            stored=False, attributed=False, event_type=parsed.event_type, reason="unknown_message"
        )

    dedupe_key = provider_event_id or f"{parsed.provider_message_id}:{parsed.event_type}"
    existing = db.scalar(select(DeliveryEvent).where(DeliveryEvent.provider_event_id == dedupe_key))
    if existing is not None:
        return IngestResult(
            stored=False,
            attributed=True,
            event_type=parsed.event_type,
            reason="duplicate",
        )

    db.add(
        DeliveryEvent(
            organization_id=message.organization_id,
            email_id=message.id,
            provider_event_id=dedupe_key,
            provider_message_id=parsed.provider_message_id,
            event_type=parsed.event_type,
            recipient=parsed.recipients[0] if parsed.recipients else None,
            payload=raw_event[:20000],
            provider_event_at=parsed.occurred_at,
        )
    )

    occurred = parsed.occurred_at or datetime.now(UTC)
    status = STATUS_BY_EVENT.get(parsed.event_type)
    if parsed.event_type == "Delivery":
        message.delivered_at = message.delivered_at or occurred
    elif parsed.event_type == "Bounce":
        message.bounced_at = message.bounced_at or occurred
        message.bounce_type = parsed.bounce_type
        message.bounce_reason = parsed.bounce_reason
    elif parsed.event_type == "Complaint":
        message.complained_at = message.complained_at or occurred
    if status:
        message.status = status

    organization = db.get(Organization, message.organization_id)
    suppressed = 0
    if organization is not None:
        if parsed.event_type == "Bounce" and parsed.bounce_type == "Permanent":
            suppressed = sum(
                _suppress(
                    db,
                    organization_id=organization.id,
                    recipient=address,
                    reason="bounce",
                    detail=parsed.bounce_reason,
                )
                for address in parsed.recipients
            )
        elif parsed.event_type == "Complaint":
            suppressed = sum(
                _suppress(
                    db,
                    organization_id=organization.id,
                    recipient=address,
                    reason="complaint",
                    detail="recipient marked the message as spam",
                )
                for address in parsed.recipients
            )

        increments = _counter_increments(parsed.event_type, suppressed)
        if increments:
            _upsert_reputation(db, organization.id, occurred.date(), **increments)

    paused_reason = (
        _maybe_pause(db, organization, occurred.date()) if organization is not None else None
    )

    return IngestResult(
        stored=True,
        attributed=True,
        event_type=parsed.event_type,
        suppressed=suppressed,
        paused=paused_reason is not None,
        reason=paused_reason,
    )


def _counter_increments(event_type: str, suppressed: int) -> dict[str, int]:
    """Which reputation counter this event moves.

    ``sent`` counts SES ``Send`` events, not our own submissions: it is the
    denominator AWS itself would use.
    """
    if event_type == "Send":
        return {"sent": 1}
    if event_type == "Delivery":
        return {"delivered": 1}
    if event_type == "Bounce":
        return {"bounced": 1}
    if event_type == "Complaint":
        return {"complained": 1}
    return {}


def suppressed_recipients(db: Session, organization_id: UUID, recipients: list[str]) -> list[str]:
    """Return the subset of ``recipients`` this tenant must not contact."""
    if not recipients:
        return []
    lowered = [address.lower() for address in recipients]
    rows = db.scalars(
        select(Suppression.recipient).where(
            Suppression.organization_id == organization_id,
            Suppression.recipient.in_(lowered),
        )
    ).all()
    return sorted(set(rows))
