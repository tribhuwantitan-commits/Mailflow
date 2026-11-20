"""Long-poll the SES event queue and hand each message to the ingest service.

Shape is deliberately the same as the outbox worker: a bounded, resumable loop with
no broker of our own. Two details matter:

* **Delete after commit.** A message is removed from SQS only once its row is
  committed. A crash in between means SNS/SQS redelivers, and the ingest dedupes on
  the SNS MessageId, so the outcome is at-least-once delivery with exactly-once
  effect.
* **Visibility timeout, not retries here.** A failed ingest leaves the message
  invisible until the queue's visibility timeout expires, then it comes back. No
  application-level retry bookkeeping, no poison-message loop of our own — SQS moves
  it to the dead-letter queue after ``maxReceiveCount``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.services.delivery_events import IngestResult, ingest

logger = logging.getLogger("mailflow.events")

#: Receive at most this many messages per call; SQS caps at 10.
BATCH = 10
#: Long-poll for this many seconds. 20 is the SQS maximum and the cheapest setting:
#: it costs one request per message rather than one per empty poll.
WAIT_SECONDS = 20


class QueueClient(Protocol):
    """The slice of SQS this poller needs, so tests can inject a fake."""

    def receive_message(self, **kwargs: Any) -> dict: ...

    def delete_message(self, **kwargs: Any) -> dict: ...


@dataclass
class PollResult:
    received: int = 0
    stored: int = 0
    duplicates: int = 0
    unattributed: int = 0
    failed: int = 0
    paused: int = 0


def _engine_from_settings(settings, create_database_engine, create_session_factory):
    """Build a worker engine with the configured pool, not the library defaults.

    Workers used to call create_database_engine() bare, so DATABASE_POOL_SIZE and
    its siblings only ever affected the API process. On a small managed database
    that difference is the whole connection budget.
    """
    engine = create_database_engine(
        settings.database_url,
        settings.database_connect_timeout_seconds,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout,
        pool_recycle=settings.database_pool_recycle,
    )
    return engine, create_session_factory(engine)


def poll_once(factory: sessionmaker[Session], client: QueueClient, queue_url: str) -> PollResult:
    """Receive one batch, ingest it, delete what was committed."""
    result = PollResult()
    response = client.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=BATCH,
        WaitTimeSeconds=WAIT_SECONDS,
        # Ask for the SNS metadata too; useful when diagnosing a bad envelope.
        AttributeNames=["All"],
    )
    messages = response.get("Messages", []) or []
    result.received = len(messages)

    for message in messages:
        body = message.get("Body", "")
        handle = message.get("ReceiptHandle")
        if not body or not handle:
            continue
        try:
            with factory() as db:
                outcome: IngestResult = ingest(db, body)
                db.commit()
        except Exception as exc:  # noqa: BLE001 - one bad message must not stop the batch
            # Never log the body: it contains recipient addresses.
            logger.warning("event_ingest_failed error=%s", type(exc).__name__)
            result.failed += 1
            continue

        if not outcome.stored:
            if outcome.reason == "duplicate":
                result.duplicates += 1
            else:
                result.unattributed += 1
        else:
            result.stored += 1
            if outcome.paused:
                result.paused += 1

        # Delete even when unattributed: retrying will not make an unknown MessageId
        # known, and a real ingest failure already took the `except` path above.
        try:
            client.delete_message(QueueUrl=queue_url, ReceiptHandle=handle)
        except Exception as exc:  # noqa: BLE001 - redelivery will dedupe
            logger.warning("event_delete_failed error=%s", type(exc).__name__)

    return result


def build_client(settings) -> QueueClient:
    """Create the SQS client from application settings."""
    import boto3

    return boto3.client(
        "sqs",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=(
            settings.aws_secret_access_key.get_secret_value()
            if settings.aws_secret_access_key
            else None
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Run one batch (default) or loop until interrupted (``--loop``)."""
    import argparse
    import time

    from app.config import Settings
    from app.database import create_database_engine, create_session_factory

    parser = argparse.ArgumentParser(description="Poll the SES event queue into Postgres.")
    parser.add_argument("--loop", action="store_true", help="keep polling until interrupted")
    parser.add_argument(
        "--queue-url", default=None, help="override SQS_EVENT_QUEUE_URL for this run"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = Settings()
    queue_url = args.queue_url or settings.sqs_event_queue_url
    if not queue_url:
        logger.error("event_poller_no_queue SQS_EVENT_QUEUE_URL is not configured")
        return 2

    engine, factory = _engine_from_settings(
        settings, create_database_engine, create_session_factory
    )
    try:
        client = build_client(settings)
        while True:
            result = poll_once(factory, client, queue_url)
            if result.received:
                logger.info(
                    "event_poll received=%d stored=%d duplicates=%d "
                    "unattributed=%d failed=%d paused=%d",
                    result.received,
                    result.stored,
                    result.duplicates,
                    result.unattributed,
                    result.failed,
                    result.paused,
                )
            if not args.loop:
                return 0
            if not result.received:
                # Long polling already waited 20s; this only guards a tight-failure loop.
                time.sleep(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
