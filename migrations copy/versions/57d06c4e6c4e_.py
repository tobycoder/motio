"""empty message

Revision ID: 57d06c4e6c4e
Revises: f8dcf85b68cb
Create Date: 2025-09-28 14:55:09.844153

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '57d06c4e6c4e'
down_revision = 'f8dcf85b68cb'
branch_labels = None
depends_on = None


PERMISSION_CHECK = "permission IN ('view','comment','suggest','edit')"
PERMISSION_CHECK_DOWN = "permission IN ('view','comment','suggest')"


def _motie_share_exists(bind) -> bool:
    insp = inspect(bind)
    return insp.has_table('motie_share')


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table('notification'):
        notif_cols = {col['name'] for col in insp.get_columns('notification')}
        if 'message' in notif_cols:
            if bind.dialect.name == 'sqlite':
                op.execute('ALTER TABLE notification DROP COLUMN message')
            else:
                with op.batch_alter_table('notification', schema=None) as batch_op:
                    batch_op.drop_column('message')

    if not _motie_share_exists(bind):
        return

    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('motie_share', recreate='always') as batch_op:
            try:
                batch_op.drop_constraint('ck_motieshare_permission', type_='check')
            except Exception:
                pass
            batch_op.create_check_constraint('ck_motieshare_permission', PERMISSION_CHECK)
    else:
        try:
            op.drop_constraint('ck_motieshare_permission', 'motie_share', type_='check')
        except Exception:
            pass
        op.create_check_constraint('ck_motieshare_permission', 'motie_share', PERMISSION_CHECK)


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table('notification'):
        notif_cols = {col['name'] for col in insp.get_columns('notification')}
        if 'message' not in notif_cols:
            with op.batch_alter_table('notification', schema=None) as batch_op:
                batch_op.add_column(sa.Column('message', sa.String(length=120), nullable=True))

    if not _motie_share_exists(bind):
        return

    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('motie_share', recreate='always') as batch_op:
            try:
                batch_op.drop_constraint('ck_motieshare_permission', type_='check')
            except Exception:
                pass
            batch_op.create_check_constraint('ck_motieshare_permission', PERMISSION_CHECK_DOWN)
    else:
        try:
            op.drop_constraint('ck_motieshare_permission', 'motie_share', type_='check')
        except Exception:
            pass
        op.create_check_constraint('ck_motieshare_permission', 'motie_share', PERMISSION_CHECK_DOWN)
