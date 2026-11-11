"""Tests for the Amazon SES provider adapter using mocked boto3."""

from uuid import uuid4

import pytest

from app.config import Settings
from app.providers.email import (
    OutboundEmail,
    PermanentProviderError,
    TemporaryProviderError,
)
from app.providers.ses import SESEmailProvider


def _make_settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        mail_provider="ses",
        aws_region="us-east-1",
        aws_access_key_id="test-access-key",
        aws_secret_access_key="test-secret-key",
        **overrides,
    )


def _make_provider(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> SESEmailProvider:
    """Build an SESEmailProvider with a mocked boto3 client."""
    sent_messages: list[dict] = []

    class FakeResponse(dict):
        def __init__(self, message_id: str):
            super().__init__({"MessageId": message_id})

    class FakeSESClient:
        def send_email(self, **kwargs):  # noqa: ARG002
            sent_messages.append(kwargs)
            return FakeResponse(message_id="ses-msg-" + uuid4().hex[:8])

    provider = SESEmailProvider(settings)
    provider._client = FakeSESClient()  # noqa: SLF001 - test override
    return provider, sent_messages


def test_ses_send_success_records_message_id(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(ses_from_email="sender@example.com")
    provider, sent = _make_provider(settings, monkeypatch)

    message = OutboundEmail(
        sender="sender@example.com",
        recipients=("recipient@example.com",),
        subject="Hello",
        text_body="Hello there",
        reply_to="reply@example.com",
        idempotency_key="idem-1",
    )

    result = provider.submit(message)

    assert result.accepted is True
    assert result.provider_message_id.startswith("ses-msg-")
    assert len(sent) == 1
    call = sent[0]
    assert call["Source"] == "sender@example.com"
    assert call["Destination"]["ToAddresses"] == ["recipient@example.com"]
    assert call["Destination"]["ReplyToAddresses"] == ["reply@example.com"]
    assert call["Message"]["Subject"]["Data"] == "Hello"
    assert call["Message"]["Body"]["Text"]["Data"] == "Hello there"
    assert "Html" not in call["Message"]["Body"]


def test_ses_send_html_and_text(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings()
    provider, sent = _make_provider(settings, monkeypatch)

    message = OutboundEmail(
        sender="sender@example.com",
        recipients=("a@example.com", "b@example.com"),
        subject="Multi",
        text_body="text body",
        html_body="<b>html body</b>",
    )

    result = provider.submit(message)

    assert result.accepted is True
    call = sent[0]
    assert call["Destination"]["ToAddresses"] == ["a@example.com", "b@example.com"]
    assert call["Message"]["Body"]["Text"]["Data"] == "text body"
    assert call["Message"]["Body"]["Html"]["Data"] == "<b>html body</b>"


def test_ses_temporary_error_retriable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings()
    provider, _ = _make_provider(settings, monkeypatch)

    import botocore.exceptions

    error_response = {
        "Error": {"Code": "Throttling", "Message": "Rate exceeded"},
        "ResponseMetadata": {"HTTPStatusCode": 400},
    }

    class FailingSES:
        def send_email(self, **kwargs):  # noqa: ARG002
            raise botocore.exceptions.ClientError(error_response, "SendEmail")

    provider._client = FailingSES()  # noqa: SLF001

    message = OutboundEmail(
        sender="sender@example.com",
        recipients=("recipient@example.com",),
        subject="T",
        text_body="body",
    )

    with pytest.raises(TemporaryProviderError):
        provider.submit(message)


def test_ses_permanent_error_not_retriable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings()
    provider, _ = _make_provider(settings, monkeypatch)

    import botocore.exceptions

    error_response = {
        "Error": {"Code": "MessageRejected", "Message": "Email address not verified"},
        "ResponseMetadata": {"HTTPStatusCode": 400},
    }

    class FailingSES:
        def send_email(self, **kwargs):  # noqa: ARG002
            raise botocore.exceptions.ClientError(error_response, "SendEmail")

    provider._client = FailingSES()  # noqa: SLF001

    message = OutboundEmail(
        sender="sender@example.com",
        recipients=("recipient@example.com",),
        subject="T",
        text_body="body",
    )

    with pytest.raises(PermanentProviderError):
        provider.submit(message)


def test_ses_missing_from_email_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(ses_from_email="")
    provider, _ = _make_provider(settings, monkeypatch)

    message = OutboundEmail(
        sender="sender@example.com",
        recipients=("recipient@example.com",),
        subject="T",
        text_body="body",
    )

    with pytest.raises(PermanentProviderError, match="SES_FROM_EMAIL"):
        provider.submit(message)


def test_ses_no_body_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings()
    provider, _ = _make_provider(settings, monkeypatch)

    message = OutboundEmail(
        sender="sender@example.com",
        recipients=("recipient@example.com",),
        subject="T",
        text_body=None,
        html_body=None,
    )

    with pytest.raises(PermanentProviderError, match="At least one body"):
        provider.submit(message)
