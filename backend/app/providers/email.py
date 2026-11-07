"""Email provider contract and a network-free in-memory test fake.

Phase 3 uses this interface with an in-memory fake; no real email is sent.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class OutboundEmail:
    """Minimal provider-neutral email value used to define the adapter boundary."""

    sender: str
    recipients: tuple[str, ...]
    subject: str
    text_body: str | None = None
    html_body: str | None = None
    reply_to: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    """Provider-neutral result returned by a submission adapter."""

    provider_message_id: str
    accepted: bool


class EmailProvider(Protocol):
    """Interface for a future email provider adapter."""

    def submit(self, message: OutboundEmail) -> SubmissionResult:
        """Accept a message for processing and return a provider result."""
        ...


class FakeEmailProvider:
    """In-memory test double; records submissions and never contacts a mail service."""

    def __init__(self) -> None:
        self.submitted_messages: list[OutboundEmail] = []

    def submit(self, message: OutboundEmail) -> SubmissionResult:
        self.submitted_messages.append(message)
        return SubmissionResult(
            provider_message_id=f"fake-{len(self.submitted_messages)}",
            accepted=True,
        )


class TemporaryProviderError(Exception):
    """A transient failure eligible for bounded retry."""


class PermanentProviderError(Exception):
    """A definitive rejection that should not be retried."""


class SimulatedEmailProvider(FakeEmailProvider):
    """Deterministic network-free provider for retry tests."""

    def __init__(self, failures: list[str] | None = None) -> None:
        super().__init__()
        self.failures = list(failures or [])
        self.calls = 0

    def submit(self, message: OutboundEmail) -> SubmissionResult:
        self.calls += 1
        outcome = self.failures.pop(0) if self.failures else "success"
        if outcome == "temporary":
            raise TemporaryProviderError("simulated temporary failure")
        if outcome == "permanent":
            raise PermanentProviderError("simulated permanent failure")
        return super().submit(message)


class IdempotentFakeEmailProvider(FakeEmailProvider):
    """In-memory model of provider dedupe, not durable across process restarts."""

    def __init__(self) -> None:
        super().__init__()
        self._results: dict[str, SubmissionResult] = {}

    def submit(self, message: OutboundEmail) -> SubmissionResult:
        if message.idempotency_key is None:
            raise ValueError("A stable provider idempotency key is required")
        prior = self._results.get(message.idempotency_key)
        if prior is not None:
            return prior
        result = super().submit(message)
        self._results[message.idempotency_key] = result
        return result
