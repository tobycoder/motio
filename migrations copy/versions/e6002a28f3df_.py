"""empty message

Revision ID: e6002a28f3df
Revises: 4b9f217317aa
Create Date: 2025-09-19 11:12:19.946637

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'e6002a28f3df'
down_revision = '4b9f217317aa'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    existing_tables = set(insp.get_table_names())
    if 'motie_partijen' not in existing_tables:
        op.create_table(
            'motie_partijen',
            sa.Column('motie_id', sa.Integer(), nullable=False),
            sa.Column('partij_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['motie_id'], ['motie.id']),
            sa.ForeignKeyConstraint(['partij_id'], ['party.id']),
            sa.PrimaryKeyConstraint('motie_id', 'partij_id')
        )

    motie_cols = {col['name'] for col in insp.get_columns('motie')}
    if 'opdracht_formulering' not in motie_cols:
        with op.batch_alter_table('motie', schema=None) as batch_op:
            batch_op.add_column(sa.Column('opdracht_formulering', sa.Text(), nullable=False))


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    motie_cols = {col['name'] for col in insp.get_columns('motie')}
    if 'opdracht_formulering' in motie_cols:
        with op.batch_alter_table('motie', schema=None) as batch_op:
            batch_op.drop_column('opdracht_formulering')

    if 'motie_partijen' in insp.get_table_names():
        op.drop_table('motie_partijen')
