"""add tenant_id to core tables

Revision ID: ff88aa99bb00
Revises: ee55ff66aa77
Create Date: 2025-10-08 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ff88aa99bb00'
down_revision = 'ee55ff66aa77'
branch_labels = None
depends_on = None


def _add_tenant_id(table_name: str):
    with op.batch_alter_table(table_name) as batch:
        batch.add_column(sa.Column('tenant_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(f'fk_{table_name}_tenant_id', 'tenant', ['tenant_id'], ['id'], ondelete='RESTRICT')
        batch.create_index(f'ix_{table_name}_tenant_id', ['tenant_id'])


def upgrade():
    for t in ['user', 'party', 'motie_share', 'notification', 'advice_session', 'motie_version', 'dashboard_layout']:
        _add_tenant_id(t)


def downgrade():
    for t in ['user', 'party', 'motie_share', 'notification', 'advice_session', 'motie_version', 'dashboard_layout']:
        with op.batch_alter_table(t) as batch:
            try:
                batch.drop_index(f'ix_{t}_tenant_id')
            except Exception:
                pass
            try:
                batch.drop_constraint(f'fk_{t}_tenant_id', type_='foreignkey')
            except Exception:
                pass
            batch.drop_column('tenant_id')

