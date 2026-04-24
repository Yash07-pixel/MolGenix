"""Add persisted report metadata columns

Revision ID: 003_report_persistence
Revises: 002_target_enrichment
Create Date: 2026-04-24 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "003_report_persistence"
down_revision = "002_target_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration upgrade."""
    op.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS molecule_ids JSON")
    op.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS file_size_bytes INTEGER")


def downgrade() -> None:
    """Revert the migration."""
    op.execute("ALTER TABLE reports DROP COLUMN IF EXISTS file_size_bytes")
    op.execute("ALTER TABLE reports DROP COLUMN IF EXISTS molecule_ids")
