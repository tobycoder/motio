"""add tenant_id to motie

Revision ID: ee55ff66aa77
Revises: dd22ee33ff44
Create Date: 2025-10-08 16:52:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ee55ff66aa77'
down_revision = 'dd22ee33ff44'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('motie') as batch:
        batch.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_motie_tenant_id', 'tenant', ['tenant_id'], ['id'], ondelete='RESTRICT')
        batch.create_index('ix_motie_tenant_id', ['tenant_id'])


def downgrade():
    with op.batch_alter_table('motie') as batch:
        try:
            batch.drop_index('ix_motie_tenant_id')
        except Exception:
            pass
        try:
            batch.drop_constraint('fk_motie_tenant_id', type_='foreignkey')
        except Exception:
            pass
        batch.drop_column('tenant_id')

