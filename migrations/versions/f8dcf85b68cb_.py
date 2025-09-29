"""empty message

Revision ID: f8dcf85b68cb
Revises: 56f0f4bfa3a5
Create Date: 2025-09-28 14:54:16.687715

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'f8dcf85b68cb'
down_revision = '56f0f4bfa3a5'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    notif_cols = {col['name'] for col in insp.get_columns('notification')}
    if 'message' not in notif_cols:
        with op.batch_alter_table('notification', schema=None) as batch_op:
            batch_op.add_column(sa.Column('message', sa.String(length=120), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    notif_cols = {col['name'] for col in insp.get_columns('notification')}
    if 'message' in notif_cols:
        with op.batch_alter_table('notification', schema=None) as batch_op:
            batch_op.drop_column('message')
