"""Establish the initial Alembic schema baseline.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-04

Phase 1 has no customer/domain/message tables yet. Alembic records this revision
in its own version table so later application entities can be added through
normal, reviewable migrations.
"""

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the empty application-schema baseline."""
    pass


def downgrade() -> None:
    """The initial baseline contains no application tables to remove."""
    pass
