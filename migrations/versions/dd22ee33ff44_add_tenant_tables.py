"""add tenant tables

Revision ID: dd22ee33ff44
Revises: cc11ddeeff00
Create Date: 2025-10-08 16:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dd22ee33ff44'
down_revision = 'cc11ddeeff00'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tenant',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column('naam', sa.String(length=120), nullable=False),
        sa.Column('actief', sa.Boolean(), nullable=False),
        sa.Column('settings', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_tenant_slug', 'tenant', ['slug'], unique=True)

    op.create_table(
        'tenant_domain',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('hostname', sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_tenant_domain_tenant_id', 'tenant_domain', ['tenant_id'])
    op.create_index('uq_tenant_domain_hostname', 'tenant_domain', ['hostname'], unique=True)


def downgrade():
    op.drop_index('uq_tenant_domain_hostname', table_name='tenant_domain')
    op.drop_index('ix_tenant_domain_tenant_id', table_name='tenant_domain')
    op.drop_table('tenant_domain')
    op.drop_index('ix_tenant_slug', table_name='tenant')
    op.drop_table('tenant')

