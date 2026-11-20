"""Per-tenant sending domains.

Revision ID: 0006_domains
Revises: 0005_quota
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_domains"
down_revision = "0005_quota"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domains",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("dkim_tokens", sa.JSON(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "domain", name="uq_domains_org_domain"),
        sa.UniqueConstraint("domain", name="uq_domains_global_domain"),
        sa.CheckConstraint("status IN ('pending', 'verified', 'failed')", name="ck_domains_status"),
        sa.CheckConstraint("domain = lower(domain)", name="ck_domains_lowercase"),
    )
    op.create_index("ix_domains_org_status", "domains", ["organization_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_domains_org_status", table_name="domains")
    op.drop_table("domains")
