"""expand motie.status length to 64

Revision ID: bb77cc88dd99
Revises: a1b2c3d4e5f6
Create Date: 2025-10-08 12:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bb77cc88dd99'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.alter_column('motie', 'status', existing_type=sa.String(length=20), type_=sa.String(length=64), existing_nullable=True)
    except Exception:
        # fallback zonder existing_type voor sommige backends
        op.alter_column('motie', 'status', type_=sa.String(length=64))


def downgrade():
    try:
        op.alter_column('motie', 'status', existing_type=sa.String(length=64), type_=sa.String(length=20), existing_nullable=True)
    except Exception:
        op.alter_column('motie', 'status', type_=sa.String(length=20))

