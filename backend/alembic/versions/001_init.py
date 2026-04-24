"""Initial migration - Create targets, molecules, reports tables

Revision ID: 001_init
Revises: 
Create Date: 2026-04-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_init'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration upgrade."""
    
    # Create targets table
    op.create_table(
        'targets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(256), nullable=False),
        sa.Column('uniprot_id', sa.String(20), nullable=True),
        sa.Column('druggability_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uniprot_id'),
    )
    op.create_index(op.f('ix_targets_name'), 'targets', ['name'], unique=False)
    op.create_index(op.f('ix_targets_uniprot_id'), 'targets', ['uniprot_id'], unique=False)
    
    # Create molecules table
    op.create_table(
        'molecules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('smiles', sa.String(2048), nullable=False),
        sa.Column('lipinski_pass', sa.Boolean(), nullable=False),
        sa.Column('sas_score', sa.Float(), nullable=True),
        sa.Column('admet_scores', sa.JSON(), nullable=True),
        sa.Column('docking_score', sa.Float(), nullable=True),
        sa.Column('is_optimized', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['target_id'], ['targets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_molecules_target_id'), 'molecules', ['target_id'], unique=False)
    op.create_index(op.f('ix_molecules_smiles'), 'molecules', ['smiles'], unique=False)
    
    # Create reports table
    op.create_table(
        'reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pdf_path', sa.String(512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['target_id'], ['targets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reports_target_id'), 'reports', ['target_id'], unique=False)


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index(op.f('ix_reports_target_id'), table_name='reports')
    op.drop_table('reports')
    
    op.drop_index(op.f('ix_molecules_smiles'), table_name='molecules')
    op.drop_index(op.f('ix_molecules_target_id'), table_name='molecules')
    op.drop_table('molecules')
    
    op.drop_index(op.f('ix_targets_uniprot_id'), table_name='targets')
    op.drop_index(op.f('ix_targets_name'), table_name='targets')
    op.drop_table('targets')
