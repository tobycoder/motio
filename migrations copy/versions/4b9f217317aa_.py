"""empty message

Revision ID: 4b9f217317aa
Revises: 5a22720e87e7
Create Date: 2025-09-19 11:08:52.780185

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from typing import Optional


# revision identifiers, used by Alembic.
revision = '4b9f217317aa'
down_revision = '5a22720e87e7'
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

    if 'motie_partijen' in insp.get_table_names():
        op.drop_table('motie_partijen')

    motie_cols = {col["name"] for col in insp.get_columns('motie')}
    if 'opdracht_formulering' not in motie_cols:
        with op.batch_alter_table('motie', schema=None) as batch_op:
            batch_op.add_column(sa.Column('opdracht_formulering', sa.Text(), nullable=False))

    if 'created_by' in motie_cols:
        fk_name = _find_fk_name('motie', 'created_by', 'user')
        with op.batch_alter_table('motie', schema=None) as batch_op:
            if fk_name:
                batch_op.drop_constraint(fk_name, type_='foreignkey')
            batch_op.drop_column('created_by')

    user_cols = {col["name"] for col in insp.get_columns('user')}
    if 'partij_id' in user_cols:
        fk_name = _find_fk_name('user', 'partij_id', 'party')
        with op.batch_alter_table('user', schema=None) as batch_op:
            if fk_name:
                batch_op.drop_constraint(fk_name, type_='foreignkey')
            batch_op.drop_column('partij_id')


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('partij_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_user_partij_id_party_id', 'party', ['partij_id'], ['id'])

    with op.batch_alter_table('motie', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=False))
        batch_op.create_foreign_key('fk_motie_created_by_user_id', 'user', ['created_by'], ['id'])
        batch_op.drop_column('opdracht_formulering')

    op.create_table(
        'motie_partijen',
        sa.Column('motie_id', sa.Integer(), nullable=False),
        sa.Column('partij_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['motie_id'], ['motie.id']),
        sa.ForeignKeyConstraint(['partij_id'], ['party.id']),
        sa.PrimaryKeyConstraint('motie_id', 'partij_id')
    )
