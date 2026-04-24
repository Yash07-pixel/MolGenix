"""Database migration script template"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration upgrade."""
    pass


def downgrade() -> None:
    """Revert the migration."""
    pass
