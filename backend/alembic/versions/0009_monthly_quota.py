"""Monthly sends and monthly recipients, alongside the daily ones.

Daily x 30 was standing in for a monthly ceiling and it is not the same thing: a
tenant can spend the whole month's allowance in one afternoon and then be told they
are "within limits" every morning. These columns pin the month directly.

The free tier is why this matters most. 50/day is 1,500/month, but a real signup does
not send 50 every day -- it bursts on release day and sits idle. 1,000/month is the
number the customer is actually promised, and it is the number the SES bill follows.

The monthly total is summed from ``usage_daily`` at read time rather than kept in a
counter: one source of truth cannot drift, and the (organization_id, usage_date)
index makes the range scan cheap.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_monthly_quota"
down_revision = "0008_plan_pricing"
branch_labels = None
depends_on = None

#: slug -> (monthly emails, monthly recipients)
MONTHLY = {
    "free": (1_000, 1_000),
    "free_card": (2_500, 2_500),
    "starter": (30_000, 30_000),
    "growth": (75_000, 75_000),
    "scale": (174_000, 174_000),
    "business": (390_000, 390_000),
}


def upgrade() -> None:
    with op.batch_alter_table("sending_plans") as batch:
        batch.add_column(
            sa.Column("monthly_email_limit", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("monthly_recipient_limit", sa.Integer(), nullable=False, server_default="0")
        )

    plans = sa.table(
        "sending_plans",
        sa.column("slug", sa.String),
        sa.column("monthly_email_limit", sa.Integer),
        sa.column("monthly_recipient_limit", sa.Integer),
    )
    for slug, (emails, recipients) in MONTHLY.items():
        op.execute(
            plans.update()
            .where(plans.c.slug == slug)
            .values(monthly_email_limit=emails, monthly_recipient_limit=recipients)
        )


def downgrade() -> None:
    with op.batch_alter_table("sending_plans") as batch:
        batch.drop_column("monthly_recipient_limit")
        batch.drop_column("monthly_email_limit")
