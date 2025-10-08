"""add advice session table

Revision ID: a1b2c3d4e5f6
Revises: f0a1c2d3e4f5
Create Date: 2025-10-08 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f0a1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table('advice_session'):
        op.create_table(
            'advice_session',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('motie_id', sa.Integer(), nullable=False),
            sa.Column('requested_by_id', sa.Integer(), nullable=False),
            sa.Column('reviewer_id', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(length=30), nullable=True),
            sa.Column('draft', sa.JSON(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('returned_at', sa.DateTime(), nullable=True),
            sa.Column('accepted_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['motie_id'], ['motie.id']),
            sa.ForeignKeyConstraint(['requested_by_id'], ['user.id']),
            sa.ForeignKeyConstraint(['reviewer_id'], ['user.id']),
        )
        op.create_index('ix_advice_session_motie_id', 'advice_session', ['motie_id'])
        op.create_index('ix_advice_session_reviewer_id', 'advice_session', ['reviewer_id'])


def downgrade():
    op.drop_index('ix_advice_session_reviewer_id', table_name='advice_session')
    op.drop_index('ix_advice_session_motie_id', table_name='advice_session')
    op.drop_table('advice_session')

