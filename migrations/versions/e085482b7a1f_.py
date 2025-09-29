"""empty message

Revision ID: e085482b7a1f
Revises: 57d06c4e6c4e
Create Date: 2025-09-28 15:56:32.859886

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'e085482b7a1f'
down_revision = '57d06c4e6c4e'
branch_labels = None
depends_on = None


def _table_exists(insp, table):
    return insp.has_table(table)


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    if not _table_exists(insp, 'motie'):
        op.create_table(
            'motie',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('titel', sa.String(length=200), nullable=False),
            sa.Column('constaterende_dat', sa.Text(), nullable=True),
            sa.Column('overwegende_dat', sa.Text(), nullable=True),
            sa.Column('opdracht_formulering', sa.Text(), nullable=False),
            sa.Column('draagt_college_op', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=True),
            sa.Column('gemeenteraad_datum', sa.String(length=40), nullable=True),
            sa.Column('agendapunt', sa.String(length=40), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('indiener_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['indiener_id'], ['user.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if not _table_exists(insp, 'advice_session'):
        op.create_table(
            'advice_session',
            sa.Column('id', sa.Integer(), nullable=False),
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
            sa.PrimaryKeyConstraint('id'),
        )

    if not _table_exists(insp, 'motie_medeindieners'):
        op.create_table(
            'motie_medeindieners',
            sa.Column('motie_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['motie_id'], ['motie.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('motie_id', 'user_id'),
            sa.UniqueConstraint('motie_id', 'user_id', name='uq_motie_user'),
        )

    if not _table_exists(insp, 'motie_share'):
        op.create_table(
            'motie_share',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('motie_id', sa.Integer(), nullable=False),
            sa.Column('created_by_id', sa.Integer(), nullable=True),
            sa.Column('target_user_id', sa.Integer(), nullable=True),
            sa.Column('target_party_id', sa.Integer(), nullable=True),
            sa.Column('permission', sa.String(length=20), nullable=False),
            sa.Column('message', sa.Text(), nullable=True),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
            sa.Column('actief', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('revoked_at', sa.DateTime(), nullable=True),
            sa.CheckConstraint("permission IN ('view','comment','suggest', 'edit')", name='ck_motieshare_permission'),
            sa.CheckConstraint(
                '(target_user_id IS NOT NULL) <> (target_party_id IS NOT NULL)',
                name='ck_motieshare_target_xor',
            ),
            sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['motie_id'], ['motie.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['target_party_id'], ['party.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['target_user_id'], ['user.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('motie_id', 'target_party_id', 'actief', name='uq_share_party_active'),
            sa.UniqueConstraint('motie_id', 'target_user_id', 'actief', name='uq_share_user_active'),
        )
        with op.batch_alter_table('motie_share', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_motie_share_created_by_id'), ['created_by_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_motie_share_motie_id'), ['motie_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_motie_share_target_party_id'), ['target_party_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_motie_share_target_user_id'), ['target_user_id'], unique=False)

    if not _table_exists(insp, 'notification'):
        op.create_table(
            'notification',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('motie_id', sa.Integer(), nullable=True),
            sa.Column('share_id', sa.Integer(), nullable=True),
            sa.Column('type', sa.String(length=50), nullable=False),
            sa.Column('payload', sa.Text(), nullable=False),
            sa.Column('read_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['motie_id'], ['motie.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['share_id'], ['motie_share.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        with op.batch_alter_table('notification', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_notification_motie_id'), ['motie_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_notification_share_id'), ['share_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_notification_user_id'), ['user_id'], unique=False)


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)

    if _table_exists(insp, 'notification'):
        with op.batch_alter_table('notification', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_notification_user_id'))
            batch_op.drop_index(batch_op.f('ix_notification_share_id'))
            batch_op.drop_index(batch_op.f('ix_notification_motie_id'))
        op.drop_table('notification')

    if _table_exists(insp, 'motie_share'):
        with op.batch_alter_table('motie_share', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_motie_share_target_user_id'))
            batch_op.drop_index(batch_op.f('ix_motie_share_target_party_id'))
            batch_op.drop_index(batch_op.f('ix_motie_share_motie_id'))
            batch_op.drop_index(batch_op.f('ix_motie_share_created_by_id'))
        op.drop_table('motie_share')

    if _table_exists(insp, 'motie_medeindieners'):
        op.drop_table('motie_medeindieners')

    if _table_exists(insp, 'advice_session'):
        op.drop_table('advice_session')

    if _table_exists(insp, 'motie'):
        op.drop_table('motie')

    if _table_exists(insp, 'user'):
        op.drop_table('user')
