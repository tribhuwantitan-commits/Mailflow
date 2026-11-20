"""Delivery events, suppressions, tenant reputation and the verification columns.

Revision ID: 0007_events
Revises: 0006_domains
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_events"
down_revision = "0006_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("email_messages") as batch:
        batch.add_column(sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("bounced_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("complained_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("bounce_type", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("bounce_reason", sa.Text(), nullable=True))

    with op.batch_alter_table("organizations") as batch:
        batch.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("card_verified_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("sending_paused_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("sending_paused_reason", sa.String(length=200), nullable=True))

    op.create_table(
        "delivery_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email_id", sa.Uuid(), nullable=True),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=True),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("provider_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_id"], ["email_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        # SNS is at-least-once; this is what makes ingest idempotent.
        sa.UniqueConstraint("provider_event_id", name="uq_delivery_events_provider_event"),
    )
    op.create_index(
        "ix_delivery_events_email", "delivery_events", ["email_id", "provider_event_at"]
    )
    op.create_index(
        "ix_delivery_events_org_received", "delivery_events", ["organization_id", "received_at"]
    )
    op.create_index(
        "ix_delivery_events_provider_message", "delivery_events", ["provider_message_id"]
    )

    op.create_table(
        "suppressions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "recipient", name="uq_suppressions_org_recipient"),
    )
    op.create_index("ix_suppressions_org_reason", "suppressions", ["organization_id", "reason"])

    op.create_table(
        "tenant_reputation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bounced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("complained", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_reason", sa.String(length=200), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "day", name="uq_tenant_reputation_day"),
    )


def downgrade() -> None:
    op.drop_table("tenant_reputation")
    op.drop_index("ix_suppressions_org_reason", table_name="suppressions")
    op.drop_table("suppressions")
    op.drop_index("ix_delivery_events_provider_message", table_name="delivery_events")
    op.drop_index("ix_delivery_events_org_received", table_name="delivery_events")
    op.drop_index("ix_delivery_events_email", table_name="delivery_events")
    op.drop_table("delivery_events")

    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("sending_paused_reason")
        batch.drop_column("sending_paused_at")
        batch.drop_column("card_verified_at")
        batch.drop_column("email_verified_at")

    with op.batch_alter_table("email_messages") as batch:
        batch.drop_column("bounce_reason")
        batch.drop_column("bounce_type")
        batch.drop_column("complained_at")
        batch.drop_column("bounced_at")
        batch.drop_column("delivered_at")
