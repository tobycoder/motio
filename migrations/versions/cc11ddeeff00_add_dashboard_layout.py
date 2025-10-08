"""add dashboard layout table

Revision ID: cc11ddeeff00
Revises: bb77cc88dd99
Create Date: 2025-10-08 16:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cc11ddeeff00'
down_revision = 'bb77cc88dd99'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dashboard_layout',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False, index=True),
        sa.Column('context', sa.String(length=50), nullable=False, index=True),
        sa.Column('layout', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'context', name='uq_dashboard_user_context'),
    )


def downgrade():
    # Dropping the table will drop related indexes
    op.drop_table('dashboard_layout')
