"""empty message

Revision ID: aa6d5689cec3
Revises: 3d4ef663f964
Create Date: 2025-09-24 09:28:09.209096

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from typing import Optional


# revision identifiers, used by Alembic.
revision = 'aa6d5689cec3'
down_revision = '3d4ef663f964'
branch_labels = None
depends_on = None


def _find_fk_name(bind: Connection, table: str, constrained_col: str, referred_table: str) -> Optional[str]:
    insp = inspect(bind)
    for fk in insp.get_foreign_keys(table):
        cols = fk.get("constrained_columns") or []
        if constrained_col in cols and fk.get("referred_table") == referred_table:
            return fk.get("name")
    return None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    amend_cols = {col['name'] for col in insp.get_columns('amendementen')}
    if 'indiener_id' not in amend_cols:
        with op.batch_alter_table('amendementen', schema=None) as batch_op:
            batch_op.add_column(sa.Column('indiener_id', sa.Integer(), nullable=False))
            fk_name = _find_fk_name(bind, 'amendementen', 'created_by', 'user')
            if fk_name:
                batch_op.drop_constraint(fk_name, type_='foreignkey')
            batch_op.create_foreign_key('fk_amendementen_indiener_id_user_id', 'user', ['indiener_id'], ['id'])
            if 'created_by' in amend_cols:
                batch_op.drop_column('created_by')

    motie_cols = {col['name'] for col in insp.get_columns('motie')}
    if 'indiener_id' in motie_cols:
        with op.batch_alter_table('motie', schema=None) as batch_op:
            batch_op.alter_column('indiener_id', existing_type=sa.Integer(), nullable=True)
    if 'Field13' in motie_cols:
        with op.batch_alter_table('motie', schema=None) as batch_op:
            batch_op.drop_column('Field13')


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    with op.batch_alter_table('motie', schema=None) as batch_op:
        batch_op.add_column(sa.Column('Field13', sa.Integer(), nullable=True))
        batch_op.alter_column('indiener_id', existing_type=sa.Integer(), nullable=False)

    amend_cols = {col['name'] for col in insp.get_columns('amendementen')}
    with op.batch_alter_table('amendementen', schema=None) as batch_op:
        if 'created_by' not in amend_cols:
            batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=False))
        fk_name = _find_fk_name(bind, 'amendementen', 'indiener_id', 'user')
        if fk_name:
            batch_op.drop_constraint(fk_name, type_='foreignkey')
        batch_op.create_foreign_key('fk_amendementen_created_by_user_id', 'user', ['created_by'], ['id'])
        if 'indiener_id' in amend_cols:
            batch_op.drop_column('indiener_id')
