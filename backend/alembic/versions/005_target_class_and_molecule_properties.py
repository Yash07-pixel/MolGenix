"""Add target classification and molecule property columns

Revision ID: 005_target_props
Revises: 004_optimization_changes
Create Date: 2026-04-25 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "005_target_props"
down_revision = "004_optimization_changes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration upgrade."""
    op.execute("ALTER TABLE targets ADD COLUMN IF NOT EXISTS target_class VARCHAR(64)")
    op.execute("ALTER TABLE molecules ADD COLUMN IF NOT EXISTS molecular_weight DOUBLE PRECISION")
    op.execute("ALTER TABLE molecules ADD COLUMN IF NOT EXISTS logp DOUBLE PRECISION")
    op.execute("ALTER TABLE molecules ADD COLUMN IF NOT EXISTS tpsa DOUBLE PRECISION")
    op.execute("ALTER TABLE molecules ADD COLUMN IF NOT EXISTS rotatable_bonds INTEGER")
    op.execute("ALTER TABLE molecules ADD COLUMN IF NOT EXISTS smiles_valid BOOLEAN DEFAULT TRUE")
    op.execute("UPDATE molecules SET smiles_valid = TRUE WHERE smiles_valid IS NULL")
    op.execute("ALTER TABLE molecules ALTER COLUMN smiles_valid SET DEFAULT TRUE")
    op.execute("ALTER TABLE molecules ALTER COLUMN smiles_valid SET NOT NULL")


def downgrade() -> None:
    """Revert the migration."""
    op.execute("ALTER TABLE molecules DROP COLUMN IF EXISTS smiles_valid")
    op.execute("ALTER TABLE molecules DROP COLUMN IF EXISTS rotatable_bonds")
    op.execute("ALTER TABLE molecules DROP COLUMN IF EXISTS tpsa")
    op.execute("ALTER TABLE molecules DROP COLUMN IF EXISTS logp")
    op.execute("ALTER TABLE molecules DROP COLUMN IF EXISTS molecular_weight")
    op.execute("ALTER TABLE targets DROP COLUMN IF EXISTS target_class")
