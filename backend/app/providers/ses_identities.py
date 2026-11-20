"""Amazon SES identity management: register, inspect and remove customer domains.

Kept apart from ``ses.py`` (which sends) because the two have different failure
tolerances: a send is retried by the outbox worker, while identity calls happen
inside an interactive request and are surfaced to the customer verbatim.

Easy DKIM is requested on registration, which is what SES turns into three CNAME
records. The customer publishes them, SES verifies, and ``check`` starts
returning ``Success``. Until then the identity exists but is unusable, which is
exactly what the ``pending`` status mirrors.
"""

from __future__ import annotations

import logging
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings
from app.services.domains import DomainError, IdentityState

logger = logging.getLogger("mailflow.providers.ses_identities")


class SESIdentityVerifier:
    """The real :class:`app.services.domains.DomainVerifier`."""

    def __init__(self, settings: Settings, ses_client: Any | None = None) -> None:
        self.settings = settings
        self._client = ses_client or boto3.client(
            "sesv2",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=(
                settings.aws_secret_access_key.get_secret_value()
                if settings.aws_secret_access_key
                else None
            ),
        )

    def register(self, domain: str) -> IdentityState:
        """Create the identity with Easy DKIM enabled, tolerating "already exists"."""
        try:
            response = self._client.create_email_identity(
                EmailIdentity=domain,
                DkimSigningAttributes={"NextSigningKeyLength": "RSA_2048_BIT"},
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "AlreadyExistsException":
                return self.check(domain)
            raise _translate(exc, domain) from exc
        except (BotoCoreError, OSError) as exc:
            raise DomainError(
                "provider_unavailable",
                "Could not reach the mail provider. Try again in a moment.",
            ) from exc

        tokens = tuple(
            attribute.get("Token", "")
            for attribute in response.get("DkimAttributes", {}).get("Tokens", [])
            if attribute.get("Token")
        )
        return IdentityState(
            exists=True,
            verified=bool(response.get("VerifiedForSendingStatus")),
            dkim_tokens=tokens,
        )

    def check(self, domain: str) -> IdentityState:
        try:
            response = self._client.get_email_identity(EmailIdentity=domain)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "NotFoundException":
                return IdentityState(exists=False, verified=False)
            raise _translate(exc, domain) from exc
        except (BotoCoreError, OSError) as exc:
            raise DomainError(
                "provider_unavailable",
                "Could not reach the mail provider. Try again in a moment.",
            ) from exc

        return IdentityState(
            exists=True,
            verified=bool(response.get("VerifiedForSendingStatus")),
            dkim_tokens=tuple(
                attribute.get("Token", "")
                for attribute in response.get("DkimAttributes", {}).get("Tokens", [])
                if attribute.get("Token")
            ),
        )

    def remove(self, domain: str) -> None:
        try:
            self._client.delete_email_identity(EmailIdentity=domain)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code != "NotFoundException":
                logger.warning("ses_identity_delete_failed domain=%s code=%s", domain, code)


def _translate(exc: ClientError, domain: str) -> DomainError:
    """Turn an SES identity error into something a customer can act on."""
    code = exc.response.get("Error", {}).get("Code", "")
    message = exc.response.get("Error", {}).get("Message", "")
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", "")
    logger.warning("ses_identity_error domain=%s code=%s status=%s", domain, code, status)

    if code in {"Throttling", "TooManyRequestsException"} or str(status).startswith("5"):
        return DomainError(
            "provider_unavailable",
            "The mail provider is busy. Try again in a moment.",
        )
    if code in {"LimitExceededException", "TooManyRequests"}:
        return DomainError(
            "provider_limit",
            "The platform has reached its domain limit with the mail provider. Contact support.",
        )
    return DomainError(
        "provider_error", f"The mail provider rejected the domain: {message or code}"
    )


class NoopDomainVerifier:
    """Stand-in used when MAIL_PROVIDER is not ``ses``.

    Marks anything as verified so development and the test suite never need AWS,
    while still exercising the ownership check: the domain row must exist and be
    verified, it is just instantly verified here.
    """

    def register(self, domain: str) -> IdentityState:
        return IdentityState(exists=True, verified=True)

    def check(self, domain: str) -> IdentityState:
        return IdentityState(exists=True, verified=True)

    def remove(self, domain: str) -> None:
        return None
