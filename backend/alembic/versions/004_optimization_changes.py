"""Add molecule optimization changes column

Revision ID: 004_optimization_changes
Revises: 003_report_persistence
Create Date: 2026-04-24 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "004_optimization_changes"
down_revision = "003_report_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration upgrade."""
    op.execute("ALTER TABLE molecules ADD COLUMN IF NOT EXISTS optimization_changes JSON")


def downgrade() -> None:
    """Revert the migration."""
    op.execute("ALTER TABLE molecules DROP COLUMN IF EXISTS optimization_changes")
