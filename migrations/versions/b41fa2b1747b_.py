"""empty message

Revision ID: b41fa2b1747b
Revises: e085482b7a1f
Create Date: 2025-09-29 14:13:07.573961

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from typing import Optional


# revision identifiers, used by Alembic.
revision = 'b41fa2b1747b'
down_revision = 'e085482b7a1f'
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
    if not insp.has_table('user'):
        return

    user_cols = {col['name'] for col in insp.get_columns('user')}
    if 'partij_id' in user_cols:
        return

    if not insp.has_table('party'):
        # nothing to relate to, skip
        return

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('partij_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_user_partij_id_party_id',
            'party',
            ['partij_id'],
            ['id']
        )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table('user'):
        return

    user_cols = {col['name'] for col in insp.get_columns('user')}
    if 'partij_id' not in user_cols:
        return

    fk_name = _find_fk_name('user', 'partij_id', 'party')
    with op.batch_alter_table('user', schema=None) as batch_op:
        if fk_name:
            batch_op.drop_constraint(fk_name, type_='foreignkey')
        batch_op.drop_column('partij_id')
