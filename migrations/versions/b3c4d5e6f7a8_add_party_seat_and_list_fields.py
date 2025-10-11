"""add seat and list number fields to party

Revision ID: b3c4d5e6f7a8
Revises: aa12bb34cc56
Create Date: 2025-10-11 14:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3c4d5e6f7a8'
down_revision = 'aa12bb34cc56'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('party', sa.Column('zetelaantal', sa.Integer(), nullable=True))
    op.add_column('party', sa.Column('lijstnummer_volgende', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('party', 'lijstnummer_volgende')
    op.drop_column('party', 'zetelaantal')
