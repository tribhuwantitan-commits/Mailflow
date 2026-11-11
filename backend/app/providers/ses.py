"""Amazon SES email provider adapter.

Uses boto3 to send emails through Amazon Simple Email Service.
Credentials and region are read from application settings.
"""

import logging
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings
from app.providers.email import (
    OutboundEmail,
    PermanentProviderError,
    SubmissionResult,
    TemporaryProviderError,
)

logger = logging.getLogger("mailflow.providers.ses")


class SESEmailProvider:
    """Amazon SES adapter for sending transactional email.

    Implements the EmailProvider protocol. Temporary SES failures
    (throttling, network timeouts, 5xx) raise TemporaryProviderError
    so the outbox worker can retry. Permanent failures (auth, invalid
    sender, invalid address) raise PermanentProviderError.
    """

    def __init__(
        self,
        settings: Settings,
        ses_client: Any | None = None,
    ) -> None:
        self.settings = settings
        self._client = ses_client or boto3.client(
            "ses",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=(
                settings.aws_secret_access_key.get_secret_value()
                if settings.aws_secret_access_key
                else None
            ),
        )

    def submit(self, message: OutboundEmail) -> SubmissionResult:
        """Accept a message and submit it to Amazon SES.

        Returns a SubmissionResult with the SES MessageId on success.
        Raises TemporaryProviderError or PermanentProviderError on failure.
        """
        if not self.settings.ses_from_email:
            raise PermanentProviderError("SES_FROM_EMAIL is not configured")

        destination: dict[str, Any] = {"ToAddresses": list(message.recipients)}
        if message.reply_to:
            destination["ReplyToAddresses"] = [message.reply_to]

        body: dict[str, Any] = {}
        if message.text_body:
            body["Text"] = {"Data": message.text_body, "Charset": "UTF-8"}
        if message.html_body:
            body["Html"] = {"Data": message.html_body, "Charset": "UTF-8"}
        if not body:
            raise PermanentProviderError("At least one body (text or html) is required")

        try:
            response = self._client.send_email(
                Source=self.settings.ses_from_email,
                Destination=destination,
                Message={
                    "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                    "Body": body,
                },
                ConfigurationSetName=self.settings.ses_configuration_set,
            )
        except ClientError as exc:
            error_response = exc.response or {}
            error_code = error_response.get("Error", {}).get("Code", "")
            error_message = error_response.get("Error", {}).get("Message", "")
            http_status = str(error_response.get("ResponseMetadata", {}).get("HTTPStatusCode", ""))
            logger.warning(
                "ses_client_error code=%s message=%s http_status=%s",
                error_code,
                error_message,
                http_status,
            )
            if self._is_temporary(error_code, error_message, http_status):
                raise TemporaryProviderError(error_message) from exc
            raise PermanentProviderError(error_message) from exc
        except (BotoCoreError, OSError) as exc:
            # Network/DNS/connection failures are temporary.
            logger.warning("ses_connection_error error=%s", type(exc).__name__)
            raise TemporaryProviderError(str(exc)) from exc

        message_id = response.get("MessageId", "")
        if not message_id:
            raise PermanentProviderError("SES did not return a MessageId")

        return SubmissionResult(
            provider_message_id=message_id,
            accepted=True,
        )

    @staticmethod
    def _is_temporary(error_code: str, error_message: str, http_status: str) -> bool:
        """Classify SES errors as temporary or permanent."""
        temporary_codes = {
            "Throttling",
            "Throttling.RateQuota",
            "InternalError",
            "ServiceUnavailable",
        }
        if error_code in temporary_codes:
            return True

        # HTTP 5xx status codes indicate temporary server-side failures.
        if http_status.startswith("5"):
            return True

        # Network/timeout keywords in the message.
        temporary_keywords = ("timeout", "network", "connection", "timed out")
        message_lower = error_message.lower()
        if any(keyword in message_lower for keyword in temporary_keywords):
            return True

        return False
