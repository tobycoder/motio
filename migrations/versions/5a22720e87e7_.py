"""empty message

Revision ID: 5a22720e87e7
Revises: ca19388fa969
Create Date: 2025-09-19 11:04:46.289810

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from typing import Optional


# revision identifiers, used by Alembic.
revision = '5a22720e87e7'
down_revision = 'ca19388fa969'
branch_labels = None
depends_on = None


def _find_fk_name(table: str, constrained_col: str, referred_table: str) -> Optional[str]:
    """Look up an FK name in a backend-agnostic way."""
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
    motie_cols = {col["name"] for col in insp.get_columns("motie")}
    if "created_by" not in motie_cols:
        return

    fk_name = _find_fk_name("motie", "created_by", "user")
    with op.batch_alter_table('motie', schema=None) as batch_op:
        if fk_name:
            batch_op.drop_constraint(fk_name, type_='foreignkey')
        batch_op.drop_column('created_by')


def downgrade():
    with op.batch_alter_table('motie', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_motie_created_by_user_id',
            'user',
            ['created_by'],
            ['id']
        )
        batch_op.alter_column('created_by', existing_type=sa.Integer(), nullable=False)
