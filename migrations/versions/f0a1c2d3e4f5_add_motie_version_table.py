"""add motie version table

Revision ID: f0a1c2d3e4f5
Revises: c3fbbdc5f1a5
Create Date: 2025-10-07 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f0a1c2d3e4f5'
down_revision = 'c3fbbdc5f1a5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'motie_version',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('motie_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('snapshot', sa.Text(), nullable=False),
        sa.Column('changed_fields', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['motie_id'], ['motie.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_id'], ['user.id'], ondelete='SET NULL'),
    )
    # Maak indices alleen als ze nog niet bestaan (idempotent)
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {ix['name'] for ix in insp.get_indexes('motie_version')}
    if 'ix_motie_version_motie_id' not in existing:
        op.create_index('ix_motie_version_motie_id', 'motie_version', ['motie_id'])
    if 'ix_motie_version_author_id' not in existing:
        op.create_index('ix_motie_version_author_id', 'motie_version', ['author_id'])


def downgrade():
    op.drop_index('ix_motie_version_author_id', table_name='motie_version')
    op.drop_index('ix_motie_version_motie_id', table_name='motie_version')
    op.drop_table('motie_version')
