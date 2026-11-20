"""Re-price the sending plans so a plan's worst case is affordable.

The original free/paid split had two problems that only show up when you multiply
the daily limit by a month:

* ``scale`` allowed 40,000 emails a day for $15. A customer who actually used it
  would send 1.2M emails a month, which costs $120 of SES against $15 of revenue.
  Every paid plan had the same shape: the daily limit was set by feel, not by what
  the price can pay for.
* ``free_card`` allowed 100 emails a day, which is 3,000 a month -- nearly the whole
  ``starter`` allowance for $0. Nobody had a reason to upgrade.

The rule applied here: a plan may spend at most ~40% of its revenue on SES, and the
daily limit is the monthly allowance divided by 30. Since quota is enforced per day
(``usage_daily``), daily x 30 *is* the monthly ceiling until a monthly counter lands.

``free_card`` also had ``per_recipient_daily_limit = 0``, which the guard reads as
"no limit" -- one address could receive all 100 sends a day. It now matches ``free``.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_plan_pricing"
down_revision = "0007_events"
branch_labels = None
depends_on = None

#: slug, name, daily emails, daily recipients, per email, per recipient, cents
#: Daily x 30 stays under what the price can pay for; see the docstring.
PLANS: tuple[tuple[str, str, int, int, int, int, int], ...] = (
    ("free", "Free", 50, 50, 5, 10, 0),
    ("free_card", "Free (card verified)", 100, 100, 10, 10, 0),
    ("starter", "Starter", 1_000, 1_000, 50, 0, 900),
    ("growth", "Growth", 2_500, 2_500, 50, 0, 1_900),
    ("scale", "Scale", 5_800, 5_800, 50, 0, 3_900),
    ("business", "Business", 13_000, 13_000, 50, 0, 7_900),
)

_OLD_LIMITS = {
    "starter": (5_000, 500),
    "growth": (15_000, 1_000),
    "scale": (40_000, 1_500),
    "business": (60_000, 2_000),
}


def upgrade() -> None:
    plans = sa.table(
        "sending_plans",
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("daily_email_limit", sa.Integer),
        sa.column("daily_recipient_limit", sa.Integer),
        sa.column("max_recipients_per_email", sa.Integer),
        sa.column("per_recipient_daily_limit", sa.Integer),
        sa.column("price_cents_usd", sa.Integer),
    )
    for slug, name, emails, recipients, per_email, per_recipient, cents in PLANS:
        op.execute(
            plans.update()
            .where(plans.c.slug == slug)
            .values(
                name=name,
                daily_email_limit=emails,
                daily_recipient_limit=recipients,
                max_recipients_per_email=per_email,
                per_recipient_daily_limit=per_recipient,
                price_cents_usd=cents,
            )
        )


def downgrade() -> None:
    plans = sa.table(
        "sending_plans",
        sa.column("slug", sa.String),
        sa.column("daily_email_limit", sa.Integer),
        sa.column("daily_recipient_limit", sa.Integer),
        sa.column("per_recipient_daily_limit", sa.Integer),
        sa.column("price_cents_usd", sa.Integer),
    )
    old_cents = {"starter": 500, "growth": 1_000, "scale": 1_500, "business": 2_000}
    for slug, (emails, cents) in _OLD_LIMITS.items():
        op.execute(
            plans.update()
            .where(plans.c.slug == slug)
            .values(
                daily_email_limit=emails,
                daily_recipient_limit=emails,
                price_cents_usd=old_cents[slug],
            )
        )
    op.execute(
        plans.update().where(plans.c.slug == "free_card").values(per_recipient_daily_limit=0)
    )
