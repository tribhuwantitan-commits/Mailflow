"""Add lease fencing and due-work indexes.

Revision ID: 0004_worker
Revises: 0003_delivery
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_worker"
down_revision = "0003_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("lease_token", sa.Uuid(), nullable=True))
    op.create_index("ix_outbox_state_next_attempt", "outbox_events", ["state", "next_attempt_at"])
    op.create_index("ix_outbox_state_lease", "outbox_events", ["state", "lease_until"])


def downgrade() -> None:
    op.drop_index("ix_outbox_state_lease", table_name="outbox_events")
    op.drop_index("ix_outbox_state_next_attempt", table_name="outbox_events")
    op.drop_column("outbox_events", "lease_token")
