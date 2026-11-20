"""Sending plans, per-tenant plan columns and the usage ledger.

Revision ID: 0005_quota
Revises: 0004_worker
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_quota"
down_revision = "0004_worker"
branch_labels = None
depends_on = None

#: Launch catalogue. Free is the default every new tenant lands on; paid tiers are
#: seeded priced so the dashboard can show them before billing exists.
PLANS = [
    # slug, name, daily emails, daily recipients, max per email, per-recipient cap, cents
    ("free", "Free", 50, 50, 5, 10, 0),
    ("free_card", "Free (card verified)", 100, 100, 10, 0, 0),
    ("starter", "Starter", 5_000, 5_000, 50, 0, 500),
    ("growth", "Growth", 15_000, 15_000, 50, 0, 1_000),
    ("scale", "Scale", 40_000, 40_000, 50, 0, 1_500),
    ("business", "Business", 60_000, 60_000, 50, 0, 2_000),
]


def upgrade() -> None:
    plans = op.create_table(
        "sending_plans",
        sa.Column("slug", sa.String(length=40), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("daily_email_limit", sa.Integer(), nullable=False),
        sa.Column("daily_recipient_limit", sa.Integer(), nullable=False),
        sa.Column("max_recipients_per_email", sa.Integer(), nullable=False),
        sa.Column("per_recipient_daily_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_cents_usd", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("daily_email_limit > 0", name="ck_sending_plans_daily_limit"),
        sa.CheckConstraint("daily_recipient_limit > 0", name="ck_sending_plans_recipient_limit"),
        sa.CheckConstraint("max_recipients_per_email > 0", name="ck_sending_plans_per_email"),
        sa.CheckConstraint("per_recipient_daily_limit >= 0", name="ck_sending_plans_per_recipient"),
        sa.CheckConstraint("price_cents_usd >= 0", name="ck_sending_plans_price"),
    )
    op.bulk_insert(
        plans,
        [
            {
                "slug": slug,
                "name": name,
                "daily_email_limit": emails,
                "daily_recipient_limit": recipients,
                "max_recipients_per_email": per_email,
                "per_recipient_daily_limit": per_recipient,
                "price_cents_usd": cents,
                "is_active": True,
            }
            for slug, name, emails, recipients, per_email, per_recipient, cents in PLANS
        ],
    )

    # Batch mode keeps SQLite (tests) working while emitting plain ALTERs on Postgres.
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(
            sa.Column("plan", sa.String(length=40), nullable=False, server_default="free")
        )
        batch.add_column(sa.Column("plan_overrides", sa.JSON(), nullable=True))
        batch.create_foreign_key(
            "fk_organizations_plan",
            "sending_plans",
            ["plan"],
            ["slug"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "usage_daily",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("emails_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recipients_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "usage_date"),
        sa.CheckConstraint("emails_sent >= 0", name="ck_usage_daily_emails"),
        sa.CheckConstraint("recipients_sent >= 0", name="ck_usage_daily_recipients"),
    )

    op.create_table(
        "recipient_daily_counts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_hash", sa.String(length=64), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id", "recipient_hash", "usage_date"),
        sa.CheckConstraint("count >= 0", name="ck_recipient_daily_counts_count"),
    )
    # Old per-recipient rows are pruned by a daily job; this index makes that scan cheap.
    op.create_index("ix_recipient_daily_counts_date", "recipient_daily_counts", ["usage_date"])


def downgrade() -> None:
    op.drop_index("ix_recipient_daily_counts_date", table_name="recipient_daily_counts")
    op.drop_table("recipient_daily_counts")
    op.drop_table("usage_daily")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_constraint("fk_organizations_plan", type_="foreignkey")
        batch.drop_column("plan_overrides")
        batch.drop_column("plan")
    op.drop_table("sending_plans")
