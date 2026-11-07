"""Tests for the network-free email provider fake."""

from app.providers.email import FakeEmailProvider, OutboundEmail


def test_fake_provider_records_submission_without_external_delivery() -> None:
    provider = FakeEmailProvider()
    message = OutboundEmail(
        sender="sender@example.test",
        recipients=("recipient@example.test",),
        subject="Test only",
        text_body="This message must not leave the process.",
    )

    result = provider.submit(message)

    assert result.accepted is True
    assert result.provider_message_id == "fake-1"
    assert provider.submitted_messages == [message]
