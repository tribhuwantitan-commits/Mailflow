"""Periodic cleanup: email body retention and the short-lived counter tables.

Why this exists at all: ``email_messages`` stores the full body of every message. At
20,000 tenants that is roughly 100 GB/month of text that nobody ever reads again —
the dashboard shows status, not content, and a recipient cannot do anything with a
six-month-old receipt. Bodies are therefore nulled after
``EMAIL_BODY_RETENTION_DAYS``; the row, its metadata and its delivery state stay.

The counter tables are the opposite problem: tiny rows, but every tenant writes one
per day. ``usage_daily`` is kept long enough for monthly reporting, the per-recipient
guard is kept only as long as the guard can be reached, and ``tenant_reputation``
keeps a quarter for trend questions.

Every delete is bounded by ``batch`` so a first run on a large table cannot lock it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.delivery import EmailMessage
from app.models.delivery_events import DeliveryEvent, TenantReputation
from app.models.quota import RecipientDailyCount, UsageDaily

logger = logging.getLogger("mailflow.maintenance")

#: Counter rows kept. The guard itself only ever looks at today.
RECIPIENT_COUNT_RETENTION_DAYS = 7
#: Kept for monthly usage reporting and invoice disputes.
USAGE_RETENTION_DAYS = 90
#: Kept for trend questions; the event log is the long-term record.
REPUTATION_RETENTION_DAYS = 90
#: The audit trail is the thing support reads when a customer says "I never got it".
DELIVERY_EVENT_RETENTION_DAYS = 90


@dataclass
class CleanupResult:
    bodies_cleared: int = 0
    usage_deleted: int = 0
    recipient_counts_deleted: int = 0
    reputation_deleted: int = 0
    delivery_events_deleted: int = 0

    def any(self) -> bool:
        return any(
            (
                self.bodies_cleared,
                self.usage_deleted,
                self.recipient_counts_deleted,
                self.reputation_deleted,
                self.delivery_events_deleted,
            )
        )


def clear_expired_bodies(
    db: Session, *, retention_days: int, batch: int = 1000, now: datetime | None = None
) -> int:
    """Null out bodies older than the retention window, keeping the metadata.

    Runs in batches by re-running the same bounded UPDATE, because a single
    unbounded statement over months of mail is exactly the kind of migration that
    takes a table lock at the worst moment.
    """
    if retention_days <= 0:
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    cleared = 0
    while True:
        # SQLite has no UPDATE ... LIMIT, so select the ids then update them; on
        # PostgreSQL this is still a bounded, indexed statement.
        ids = db.scalars(
            select(EmailMessage.id)
            .where(
                EmailMessage.created_at < cutoff,
                (EmailMessage.text_body.is_not(None)) | (EmailMessage.html_body.is_not(None)),
            )
            .limit(batch)
        ).all()
        if not ids:
            break
        db.execute(
            update(EmailMessage)
            .where(EmailMessage.id.in_(ids))
            .values(text_body=None, html_body=None)
        )
        db.commit()
        cleared += len(ids)
        if len(ids) < batch:
            break
    return cleared


def purge_counters(db: Session, *, batch: int = 5000, today: date | None = None) -> CleanupResult:
    """Delete counter and audit rows past their retention windows."""
    current = today or datetime.now(UTC).date()
    result = CleanupResult()

    def sweep(model, column, days: int) -> int:
        cutoff = current - timedelta(days=days)
        removed = 0
        while True:
            # Select the stale values, delete only those, repeat. Bounding by the
            # column rather than by primary key keeps this working for tables whose
            # key is composite (usage_daily) as well as surrogate-key ones.
            stale = db.execute(select(column).where(column < cutoff).limit(batch)).scalars().all()
            if not stale:
                return removed
            db.execute(delete(model).where(column.in_(stale)))
            db.commit()
            removed += len(stale)
            if len(stale) < batch:
                return removed

    result.usage_deleted = sweep(UsageDaily, UsageDaily.usage_date, USAGE_RETENTION_DAYS)
    result.recipient_counts_deleted = sweep(
        RecipientDailyCount,
        RecipientDailyCount.usage_date,
        RECIPIENT_COUNT_RETENTION_DAYS,
    )
    result.reputation_deleted = sweep(
        TenantReputation, TenantReputation.day, REPUTATION_RETENTION_DAYS
    )
    result.delivery_events_deleted = sweep(
        DeliveryEvent,
        DeliveryEvent.received_at,
        DELIVERY_EVENT_RETENTION_DAYS,
    )
    return result


def run(
    db: Session, *, body_retention_days: int, batch: int = 1000, today: date | None = None
) -> CleanupResult:
    """One maintenance pass: bodies first, then the small tables."""
    result = purge_counters(db, batch=batch, today=today)
    result.bodies_cleared = clear_expired_bodies(
        db, retention_days=body_retention_days, batch=batch
    )
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry point, meant for a daily scheduled task."""
    import argparse

    from app.config import Settings
    from app.database import create_database_engine, create_session_factory

    parser = argparse.ArgumentParser(description="Retention and counter cleanup.")
    parser.add_argument("--batch", type=int, default=1000)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what the retention windows are, without deleting",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = Settings()
    engine = create_database_engine(settings.database_url)
    try:
        factory = create_session_factory(engine)
        if args.dry_run:
            logger.info(
                "maintenance_windows bodies=%dd usage=%dd recipient_counts=%dd "
                "reputation=%dd delivery_events=%dd",
                settings.email_body_retention_days,
                USAGE_RETENTION_DAYS,
                RECIPIENT_COUNT_RETENTION_DAYS,
                REPUTATION_RETENTION_DAYS,
                DELIVERY_EVENT_RETENTION_DAYS,
            )
            return 0
        with factory() as db:
            result = run(
                db, body_retention_days=settings.email_body_retention_days, batch=args.batch
            )
        logger.info(
            "maintenance_done bodies_cleared=%d usage=%d recipient_counts=%d "
            "reputation=%d delivery_events=%d",
            result.bodies_cleared,
            result.usage_deleted,
            result.recipient_counts_deleted,
            result.reputation_deleted,
            result.delivery_events_deleted,
        )
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
