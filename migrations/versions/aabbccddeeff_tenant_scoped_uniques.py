"""make uniques tenant-scoped for user and party

Revision ID: aabbccddeeff
Revises: ff88aa99bb00
Create Date: 2025-10-08 17:08:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'aabbccddeeff'
down_revision = 'ff88aa99bb00'
branch_labels = None
depends_on = None


def _drop_unique_if_exists(bind, table: str, column: str):
    insp = inspect(bind)
    # try constraints
    for uc in insp.get_unique_constraints(table):
        cols = uc.get('column_names') or []
        name = uc.get('name')
        if column in cols:
            try:
                op.drop_constraint(name, table, type_='unique')
            except Exception:
                pass
    # try indexes
    for ix in insp.get_indexes(table):
        cols = ix.get('column_names') or []
        name = ix.get('name')
        unique = ix.get('unique', False)
        if unique and cols == [column]:
            try:
                op.drop_index(name, table_name=table)
            except Exception:
                pass


def upgrade():
    bind = op.get_bind()
    # user.email -> (tenant_id, email)
    _drop_unique_if_exists(bind, 'user', 'email')
    try:
        op.create_unique_constraint('uq_user_tenant_email', 'user', ['tenant_id', 'email'])
    except Exception:
        pass

    # party.naam & party.afkorting -> scoped per tenant
    _drop_unique_if_exists(bind, 'party', 'naam')
    _drop_unique_if_exists(bind, 'party', 'afkorting')
    try:
        op.create_unique_constraint('uq_party_tenant_naam', 'party', ['tenant_id', 'naam'])
    except Exception:
        pass
    try:
        op.create_unique_constraint('uq_party_tenant_afkorting', 'party', ['tenant_id', 'afkorting'])
    except Exception:
        pass


def downgrade():
    # Best-effort rollback: drop tenant-scoped uniques; original globals may or may not be recreated
    for name in ['uq_user_tenant_email', 'uq_party_tenant_naam', 'uq_party_tenant_afkorting']:
        try:
            op.drop_constraint(name, table_name=name.split('_')[1], type_='unique')
        except Exception:
            pass
    # Optionally recreate global uniques (commented out to avoid collisions if data violates them)
    # op.create_unique_constraint('uq_user_email', 'user', ['email'])
    # op.create_unique_constraint('uq_party_naam', 'party', ['naam'])
    # op.create_unique_constraint('uq_party_afkorting', 'party', ['afkorting'])

