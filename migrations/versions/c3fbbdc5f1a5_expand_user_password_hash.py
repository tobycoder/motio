"""expand user password hash length

Revision ID: c3fbbdc5f1a5
Revises: b41fa2b1747b
Create Date: 2025-09-29 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3fbbdc5f1a5'
down_revision = 'b41fa2b1747b'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'user',
        'password_hash',
        existing_type=sa.String(length=120),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        'user',
        'password_hash',
        existing_type=sa.String(length=255),
        type_=sa.String(length=120),
        existing_nullable=False,
    )
