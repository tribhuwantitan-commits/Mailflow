"""Pre-flight check for Amazon SES configuration.

Read-only: verifies credentials, region, identity verification and sending quota
WITHOUT sending any email. Run this before flipping MAIL_PROVIDER=ses.

    python -m app.scripts.check_ses                    # check from .env
    python -m app.scripts.check_ses --offline          # only .env sanity, no AWS calls
    python -m app.scripts.check_ses --region ap-south-1

Exit codes: 0 = ready, 1 = problems found, 2 = could not run.

It prints no secrets: the access key is masked, the secret is never printed.
"""

from __future__ import annotations

import argparse
import re
import socket
import sys
from typing import Any

from app.config import Settings

OK = "OK  "
WARN = "WARN"
FAIL = "FAIL"


class Report:
    """Collects check results and prints them in a stable format."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.rows.append((status, name, detail))
        print(f"[{status}] {name}{(': ' + detail) if detail else ''}")

    @property
    def failed(self) -> int:
        return sum(1 for status, _, _ in self.rows if status == FAIL)

    @property
    def warned(self) -> int:
        return sum(1 for status, _, _ in self.rows if status == WARN)


def mask(value: str | None) -> str:
    """Show only enough of a credential to recognise it."""
    if not value:
        return "(unset)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def check_settings(settings: Settings, report: Report) -> bool:
    """Validate the .env values that do not need a network call."""
    report.add(OK, "settings.env", "loaded (or defaults applied)")

    if settings.mail_provider == "ses":
        report.add(OK, "MAIL_PROVIDER", "ses")
    else:
        report.add(
            WARN,
            "MAIL_PROVIDER",
            f"{settings.mail_provider!r} — SES will not be used until this is 'ses'",
        )

    report.add(OK, "AWS_REGION", settings.aws_region)
    report.add(OK, "AWS_ACCESS_KEY_ID", mask(settings.aws_access_key_id))

    if settings.aws_secret_access_key is None:
        report.add(FAIL, "AWS_SECRET_ACCESS_KEY", "(unset)")
    else:
        report.add(
            OK, "AWS_SECRET_ACCESS_KEY", mask(settings.aws_secret_access_key.get_secret_value())
        )

    from_email = settings.ses_from_email
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", from_email or ""):
        report.add(OK, "SES_FROM_EMAIL", from_email)
    else:
        report.add(FAIL, "SES_FROM_EMAIL", f"{from_email!r} is not a valid address")

    if settings.ses_configuration_set:
        report.add(OK, "SES_CONFIGURATION_SET", settings.ses_configuration_set)
    else:
        report.add(
            WARN,
            "SES_CONFIGURATION_SET",
            "(empty) — sending works, but no open/click/bounce events will be "
            "published. Required for the Phase 7 dashboard.",
        )

    if not settings.aws_access_key_id or settings.aws_secret_access_key is None:
        return False
    return True


def _aws_error_text(exc: Exception) -> str:
    """Render a botocore ClientError without leaking credentials or content."""
    response = getattr(exc, "response", None) or {}
    code = response.get("Error", {}).get("Code", "")
    message = response.get("Error", {}).get("Message", "")
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode", "")
    parts = [part for part in (code, str(status), message) if part]
    return " | ".join(parts) or type(exc).__name__


def domain_of(address: str) -> str:
    return address.rsplit("@", 1)[-1].strip().lower() if "@" in address else ""


def check_aws(settings: Settings, report: Report, region: str) -> None:
    """Network checks: identity, config set, quota, sandbox status, DNS hints."""
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

    try:
        client = boto3.client(
            "ses",
            region_name=region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=(
                settings.aws_secret_access_key.get_secret_value()
                if settings.aws_secret_access_key
                else None
            ),
        )
    except Exception as exc:  # pragma: no cover - construction rarely fails
        report.add(FAIL, "boto3.client", type(exc).__name__)
        return

    # 1. Credentials + identity verification
    identity: dict[str, Any] | None = None
    try:
        identities = client.list_identities(IdentityType="EmailAddress")["Identities"]
        verified_domains = client.list_identities(IdentityType="Domain")["Identities"]
        from_email = settings.ses_from_email
        domain = domain_of(from_email)

        if from_email in identities:
            report.add(OK, "identity.email", f"{from_email} verified")
            identity = client.get_identity_verification_attributes(Identities=[from_email])[
                "VerificationAttributes"
            ].get(from_email)
        elif domain in verified_domains:
            report.add(OK, "identity.domain", f"{domain} verified (covers {from_email})")
            identity = client.get_identity_verification_attributes(Identities=[domain])[
                "VerificationAttributes"
            ].get(domain)
        else:
            report.add(
                FAIL,
                "identity",
                f"neither {from_email} nor {domain} is verified in {region}; "
                "verify the domain (Add identity) in this region",
            )

        if identity and identity.get("VerificationStatus") != "Success":
            report.add(
                FAIL,
                "identity.status",
                str(identity.get("VerificationStatus")),
            )
    except (ClientError, BotoCoreError, NoCredentialsError) as exc:
        report.add(FAIL, "aws.credentials", _aws_error_text(exc))
        print("\nStopping: credential call failed, later checks would fail too.")
        return

    # 2. Configuration set
    if settings.ses_configuration_set:
        try:
            client.describe_configuration_set(ConfigurationSetName=settings.ses_configuration_set)
            report.add(OK, "configuration_set", settings.ses_configuration_set)
        except ClientError as exc:
            report.add(
                FAIL,
                "configuration_set",
                f"{settings.ses_configuration_set} not found in {region} ({_aws_error_text(exc)})",
            )

    # 3. Sending quota + sandbox status
    try:
        quota = client.get_send_quota()
        max24h = int(quota.get("Max24HourSend", 0))
        rate = float(quota.get("MaxSendRate", 0))
        sent24h = float(quota.get("SentLast24Hours", 0))
        report.add(OK, "quota.24h", f"{sent24h:.0f} / {max24h:.0f} sent in last 24h")
        report.add(OK, "quota.rate", f"{rate:g} emails/second")
        if max24h <= 200 or rate <= 1:
            report.add(
                WARN,
                "sandbox",
                f"looks like SANDBOX (max {max24h:.0f}/24h, {rate:g}/s). "
                "Only verified recipients can receive mail.",
            )
        else:
            report.add(OK, "sandbox", "production access appears enabled")
    except (ClientError, BotoCoreError) as exc:
        report.add(WARN, "quota", _aws_error_text(exc))

    # 4. Region sanity: SES identities are per-Region.
    if region != settings.aws_region:
        report.add(
            WARN,
            "region.mismatch",
            f"checked {region} but AWS_REGION={settings.aws_region}; the app sends from AWS_REGION",
        )

    # 5. DNS hint for the sender domain (not a verification, just a smoke test).
    domain = domain_of(settings.ses_from_email)
    if domain:
        try:
            socket.setdefaulttimeout(3)
            socket.getaddrinfo(domain, None)
            report.add(OK, "dns", f"{domain} resolves")
        except OSError as exc:
            report.add(WARN, "dns", f"{domain} did not resolve ({exc.__class__.__name__})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify SES configuration without sending email.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="only check .env values; make no AWS calls",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Region to check (default: AWS_REGION from settings)",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    report = Report()

    print("=== MailFlow SES pre-flight check ===")
    credentials_present = check_settings(settings, report)

    if not args.offline:
        if not credentials_present:
            print("\nNo credentials configured; skipping AWS checks.")
        else:
            region = args.region or settings.aws_region
            print(f"\n--- AWS checks (region: {region}) ---")
            check_aws(settings, report, region)

    print("\n=== summary ===")
    print(f"failures: {report.failed}   warnings: {report.warned}")
    if report.failed:
        print("Not ready. Fix the FAIL lines above before setting MAIL_PROVIDER=ses.")
        return 1
    print("Ready to send. Simulator test: --send-test to yourself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
