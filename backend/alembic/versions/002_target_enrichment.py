"""Add target enrichment columns to targets

Revision ID: 002_target_enrichment
Revises: 001_init
Create Date: 2026-04-24 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "002_target_enrichment"
down_revision = "001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration upgrade."""
    op.execute("ALTER TABLE targets ADD COLUMN IF NOT EXISTS chembl_id VARCHAR(64)")
    op.execute("ALTER TABLE targets ADD COLUMN IF NOT EXISTS disease VARCHAR(256)")
    op.execute("ALTER TABLE targets ADD COLUMN IF NOT EXISTS pdb_id VARCHAR(32)")
    op.execute("ALTER TABLE targets ADD COLUMN IF NOT EXISTS known_inhibitors JSON")
    op.execute("ALTER TABLE targets ADD COLUMN IF NOT EXISTS function VARCHAR")
    op.execute("ALTER TABLE targets ADD COLUMN IF NOT EXISTS druggability_breakdown JSON")
    op.execute("ALTER TABLE targets ADD COLUMN IF NOT EXISTS pipeline_complete BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE targets ADD COLUMN IF NOT EXISTS pipeline_error VARCHAR")
    op.execute("ALTER TABLE targets ALTER COLUMN pipeline_complete SET DEFAULT FALSE")
    op.execute("UPDATE targets SET pipeline_complete = FALSE WHERE pipeline_complete IS NULL")
    op.execute("ALTER TABLE targets ALTER COLUMN pipeline_complete SET NOT NULL")


def downgrade() -> None:
    """Revert the migration."""
    op.execute("ALTER TABLE targets DROP COLUMN IF EXISTS pipeline_error")
    op.execute("ALTER TABLE targets DROP COLUMN IF EXISTS pipeline_complete")
    op.execute("ALTER TABLE targets DROP COLUMN IF EXISTS druggability_breakdown")
    op.execute("ALTER TABLE targets DROP COLUMN IF EXISTS function")
    op.execute("ALTER TABLE targets DROP COLUMN IF EXISTS known_inhibitors")
    op.execute("ALTER TABLE targets DROP COLUMN IF EXISTS pdb_id")
    op.execute("ALTER TABLE targets DROP COLUMN IF EXISTS disease")
    op.execute("ALTER TABLE targets DROP COLUMN IF EXISTS chembl_id")
