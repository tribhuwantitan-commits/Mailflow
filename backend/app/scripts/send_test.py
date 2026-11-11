"""Deliberate single test send through Amazon SES.

This is the only script in the repo that sends real email, and it only ever sends
one message, to addresses you pass explicitly. It is meant to answer one question:
"do my credentials actually deliver?"

    # cheapest, zero-cost-ish check: SES mailbox simulator (never hits a real inbox)
    python -m app.scripts.send_test --to success@simulator.amazonses.com

    # real inbox check (sandbox mode requires a VERIFIED recipient)
    python -m app.scripts.send_test --to you@yourdomain.com

Refuses to run when MAIL_PROVIDER is not "ses", so it can never be triggered by
accident in a fake-provider environment.
"""

from __future__ import annotations

import argparse
import sys

from app.config import Settings
from app.providers.email import OutboundEmail, PermanentProviderError, TemporaryProviderError
from app.providers.ses import SESEmailProvider

SIMULATOR_SUCCESS = "success@simulator.amazonses.com"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send ONE test email via SES.")
    parser.add_argument("--to", required=True, help="recipient address")
    parser.add_argument("--subject", default="MailFlow SES test", help="subject line")
    parser.add_argument(
        "--body",
        default="This is a single test message sent by backend/app/scripts/send_test.py.",
        help="plain-text body",
    )
    parser.add_argument(
        "--sender",
        default=None,
        help="From address (default: SES_FROM_EMAIL from settings)",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    if settings.mail_provider != "ses":
        print(
            f"Refusing to send: MAIL_PROVIDER is {settings.mail_provider!r}. "
            "Set MAIL_PROVIDER=ses in backend/.env first."
        )
        return 2

    sender = args.sender or settings.ses_from_email
    if args.to.strip().lower() == sender.strip().lower():
        print("Refusing to send: --to is the same as the From address.")
        return 2

    provider = SESEmailProvider(settings)
    message = OutboundEmail(
        sender=sender,
        recipients=(args.to,),
        subject=args.subject,
        text_body=args.body,
        idempotency_key="manual-test",
    )

    print(f"from: {sender}")
    print(f"to:   {args.to}")
    print(f"cfg:  {settings.ses_configuration_set or '(none)'}")
    try:
        result = provider.submit(message)
    except PermanentProviderError as exc:
        print(f"\nPERMANENT failure (do not retry): {exc}")
        print("Typical causes: unverified sender, unverified recipient in sandbox,")
        print("wrong region, missing config set, or invalid credentials.")
        return 1
    except TemporaryProviderError as exc:
        print(f"\nTEMPORARY failure (retry later): {exc}")
        print("Typical causes: throttling, quota exhausted, SES 5xx, network.")
        return 1

    print(f"\naccepted: provider_message_id={result.provider_message_id}")
    print("This is an acceptance receipt only — not proof of delivery.")
    if args.to.lower() == SIMULATOR_SUCCESS:
        print("Simulator address: SES counted it, nothing was delivered anywhere.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
