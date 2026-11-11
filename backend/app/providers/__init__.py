"""External service interfaces and local fakes."""

from typing import TYPE_CHECKING

from app.providers.email import (
    EmailProvider,
    OutboundEmail,
    SubmissionResult,
)  # noqa: F401

if TYPE_CHECKING:
    from app.config import Settings


def get_email_provider(settings: "Settings") -> EmailProvider:
    """Return the configured email provider.

    When MAIL_PROVIDER=ses, returns an Amazon SES adapter.
    Otherwise returns the fake, network-free provider.
    """
    if settings.mail_provider == "ses":
        from app.providers.ses import SESEmailProvider  # noqa: F401

        return SESEmailProvider(settings)
    from app.providers.email import FakeEmailProvider  # noqa: F401

    return FakeEmailProvider()


__all__ = [
    "EmailProvider",
    "OutboundEmail",
    "SubmissionResult",
    "get_email_provider",
]
