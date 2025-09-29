"""add motie_medeindieners m2m

Revision ID: 2c475353cb92
Revises: 46e872738514
Create Date: 2025-09-23 22:06:38.853811

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from typing import Optional


# revision identifiers, used by Alembic.
revision = '2c475353cb92'
down_revision = '46e872738514'
branch_labels = None
depends_on = None


def _find_fk_name(table: str, constrained_col: str, referred_table: str) -> Optional[str]:
    bind = op.get_bind()
    insp = inspect(bind)
    for fk in insp.get_foreign_keys(table):
        cols = fk.get("constrained_columns") or []
        if constrained_col in cols and fk.get("referred_table") == referred_table:
            return fk.get("name")
    return None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    tables = set(insp.get_table_names())
    if 'motie_medeindieners' not in tables:
        op.create_table(
            'motie_medeindieners',
            sa.Column('motie_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['motie_id'], ['motie.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('motie_id', 'user_id'),
            sa.UniqueConstraint('motie_id', 'user_id', name='uq_motie_user')
        )

    if 'motie_partijen' in tables:
        op.drop_table('motie_partijen')

    motie_cols = {col['name'] for col in insp.get_columns('motie')}
    if 'indiener_id' not in motie_cols:
        with op.batch_alter_table('motie', schema=None) as batch_op:
            batch_op.add_column(sa.Column('indiener_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_motie_indiener_id_user_id',
                'user',
                ['indiener_id'],
                ['id']
            )
    if 'created_by' in motie_cols:
        fk_name = _find_fk_name('motie', 'created_by', 'user')
        with op.batch_alter_table('motie', schema=None) as batch_op:
            if fk_name:
                batch_op.drop_constraint(fk_name, type_='foreignkey')
            batch_op.drop_column('created_by')


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    motie_cols = {col['name'] for col in insp.get_columns('motie')}
    fk_name = _find_fk_name('motie', 'indiener_id', 'user')
    with op.batch_alter_table('motie', schema=None) as batch_op:
        if 'created_by' not in motie_cols:
            batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=False))
        if fk_name:
            batch_op.drop_constraint(fk_name, type_='foreignkey')
        if 'indiener_id' in motie_cols:
            batch_op.drop_column('indiener_id')
        batch_op.create_foreign_key('fk_motie_created_by_user_id', 'user', ['created_by'], ['id'])

    tables = set(insp.get_table_names())
    if 'motie_partijen' not in tables:
        op.create_table(
            'motie_partijen',
            sa.Column('motie_id', sa.Integer(), nullable=False),
            sa.Column('partij_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['motie_id'], ['motie.id']),
            sa.ForeignKeyConstraint(['partij_id'], ['party.id']),
            sa.PrimaryKeyConstraint('motie_id', 'partij_id')
        )
    if 'motie_medeindieners' in tables:
        op.drop_table('motie_medeindieners')
