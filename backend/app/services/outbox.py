"""Bounded, lease-fenced outbox worker; fake provider only."""

import json
import logging
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.models.delivery import EmailMessage, OutboxEvent
from app.providers.email import (
    EmailProvider,
    OutboundEmail,
    PermanentProviderError,
    TemporaryProviderError,
)

logger = logging.getLogger("mailflow.worker")
MAX_ATTEMPTS = 5
LEASE_SECONDS = 120
HEARTBEAT_SECONDS = 30


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def backoff(attempt: int) -> timedelta:
    """Retry at 20, 40, 80, 160 seconds (cap one hour)."""
    return timedelta(seconds=min(3600, 10 * 2 ** min(attempt, 9)))


def eligible(now: datetime):
    return or_(
        (OutboxEvent.state == "pending") & (OutboxEvent.next_attempt_at <= now),
        (OutboxEvent.state == "leased") & (OutboxEvent.lease_until <= now),
    )


def renew_lease(factory: sessionmaker[Session], event_id: UUID, token: UUID) -> bool:
    """Extend only the currently held lease; a replaced worker cannot renew it."""
    with factory() as db:
        changed = db.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.id == event_id,
                OutboxEvent.state == "leased",
                OutboxEvent.lease_token == token,
                OutboxEvent.lease_until > now_utc(),
            )
            .values(lease_until=now_utc() + timedelta(seconds=LEASE_SECONDS))
        ).rowcount
        db.commit()
        return changed == 1


def _heartbeat(factory: sessionmaker[Session], event_id: UUID, token: UUID, stop: Event) -> None:
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            if not renew_lease(factory, event_id, token):
                logger.warning("worker_lease_lost event_id=%s", event_id)
                return
        except Exception:
            # Database exception text can contain connection details; log only a safe event ID.
            logger.warning("worker_lease_renewal_failed event_id=%s", event_id)
            return


def process_event(factory: sessionmaker[Session], provider: EmailProvider, event_id: UUID) -> bool:
    """Atomically claim once, heartbeat during send, and fence stale completions.

    A crashed worker's lease is recoverable. External provider acceptance remains
    at-least-once unless the provider honors OutboundEmail.idempotency_key.
    """
    token = uuid4()
    now = now_utc()
    with factory() as db:
        claimed = db.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id, eligible(now))
            .values(
                state="leased",
                lease_until=now + timedelta(seconds=LEASE_SECONDS),
                lease_token=token,
            )
        ).rowcount
        if claimed != 1:
            db.rollback()
            return False
        event = db.get(OutboxEvent, event_id)
        message = db.get(EmailMessage, event.email_id)
        if message.attempt_count >= MAX_ATTEMPTS:
            message.status = "failed"
            message.error_code = "attempts_exhausted"
            event.state = "done"
            event.lease_until = None
            event.lease_token = None
            db.commit()
            logger.warning(
                "worker_attempts_exhausted event_id=%s email_id=%s", event_id, message.id
            )
            return True
        message.status = "sending"
        message.attempt_count += 1
        attempt = message.attempt_count
        outbound = OutboundEmail(
            sender=message.sender,
            recipients=tuple(json.loads(message.recipients)),
            subject=message.subject,
            text_body=message.text_body,
            html_body=message.html_body,
            reply_to=message.reply_to,
            idempotency_key=str(message.id),
        )
        db.commit()

        stop = Event()
        heartbeat = Thread(target=_heartbeat, args=(factory, event_id, token, stop), daemon=True)
        heartbeat.start()
        outcome = "sent"
        result = None
        try:
            result = provider.submit(outbound)
            if not result.accepted:
                outcome = "permanent_provider_error"
        except TemporaryProviderError:
            outcome = "temporary_provider_error"
        except PermanentProviderError:
            outcome = "permanent_provider_error"
        except Exception:
            # Do not log exception text: provider exceptions may contain message content.
            outcome = "provider_error"
        finally:
            stop.set()
            heartbeat.join()

        with factory() as db:
            # The conditional update locks the event row until the message update commits.
            # A worker whose lease was replaced cannot overwrite a newer result.
            changed = db.execute(
                update(OutboxEvent)
                .where(
                    OutboxEvent.id == event_id,
                    OutboxEvent.state == "leased",
                    OutboxEvent.lease_token == token,
                )
                .values(state="done", lease_until=None, lease_token=None)
            ).rowcount
            if changed != 1:
                db.rollback()
                logger.warning("worker_stale_completion event_id=%s", event_id)
                return False
            event = db.get(OutboxEvent, event_id)
            message = db.get(EmailMessage, event.email_id)
            if outcome == "sent":
                # "sent" means the provider ACCEPTED the message, not that the
                # recipient's server delivered it. Delivery/bounce state arrives
                # later through SES event publishing (see docs/DELIVERY-EVENTS.md).
                message.status = "sent"
                message.provider = result.provider_name
                message.provider_message_id = result.provider_message_id
                message.error_code = None
            else:
                message.error_code = outcome
                if outcome == "permanent_provider_error" or attempt >= MAX_ATTEMPTS:
                    message.status = "failed"
                else:
                    message.status = "queued"
                    event.state = "pending"
                    event.next_attempt_at = now_utc() + backoff(attempt)
            db.commit()
            logger.info(
                "worker_result event_id=%s email_id=%s attempt=%d outcome=%s",
                event_id,
                event.email_id,
                attempt,
                outcome,
            )
            return True


def process_due(factory: sessionmaker[Session], provider: EmailProvider, limit: int = 50) -> int:
    """Run a bounded tick; competing workers safely skip claimed events."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    with factory() as db:
        ids = db.scalars(
            select(OutboxEvent.id)
            .where(eligible(now_utc()))
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(limit)
        ).all()
        return sum(process_event(factory, provider, event_id) for event_id in ids)


def worker_status(factory: sessionmaker[Session]) -> dict[str, int]:
    """Aggregate operational counts without loading customer email content."""
    now = now_utc()
    with factory() as db:
        pending = db.scalar(
            select(func.count()).select_from(OutboxEvent).where(OutboxEvent.state == "pending")
        )
        due = db.scalar(select(func.count()).select_from(OutboxEvent).where(eligible(now)))
        leased = db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.state == "leased", OutboxEvent.lease_until > now)
        )
        failed = db.scalar(
            select(func.count()).select_from(EmailMessage).where(EmailMessage.status == "failed")
        )
        return {"pending": pending, "due": due, "leased": leased, "failed": failed}


def requeue_failed(factory: sessionmaker[Session], email_id: UUID) -> bool:
    """Explicit operator recovery; never automatically retry permanent failures."""
    with factory() as db:
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.email_id == email_id))
        if event is None:
            return False
        message = db.get(EmailMessage, email_id)
        if event.state != "done" or message.status != "failed":
            return False
        event.state = "pending"
        event.next_attempt_at = now_utc()
        event.lease_token = None
        event.lease_until = None
        message.status = "queued"
        message.attempt_count = 0
        message.error_code = None
        db.commit()
        logger.warning("worker_manual_requeue email_id=%s", email_id)
        return True


def main() -> None:
    """Run one bounded outbox worker tick, or view status/requeue from CLI."""
    import argparse

    from app.config import Settings
    from app.database import create_database_engine, create_session_factory
    from app.providers import get_email_provider

    parser = argparse.ArgumentParser(description="MailFlow outbox worker")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--requeue", type=UUID, metavar="EMAIL_ID")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = Settings()
    engine = create_database_engine(settings.database_url)
    try:
        factory = create_session_factory(engine)
        provider = get_email_provider(settings)
        if args.status:
            logger.info("worker_status %s", worker_status(factory))
        elif args.requeue:
            logger.info(
                "worker_requeue_result email_id=%s success=%s",
                args.requeue,
                requeue_failed(factory, args.requeue),
            )
        else:
            count = process_due(factory, provider)
            logger.info("worker_tick processed=%d status=%s", count, worker_status(factory))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
