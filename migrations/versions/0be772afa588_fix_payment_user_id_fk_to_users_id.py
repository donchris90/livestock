"""Fix Payment.user_id FK to users.id

Revision ID: 0be772afa588
Revises: 0a3818c7d8f1
Create Date: 2025-07-18 11:55:26.559784

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0be772afa588'
down_revision = '0a3818c7d8f1'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
