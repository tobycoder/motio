"""add user email_prefs

Revision ID: aa12bb34cc56
Revises: aabbccddeeff
Create Date: 2025-10-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aa12bb34cc56'
down_revision = 'aabbccddeeff'
branch_labels = None
depends_on = None


def upgrade():
    # Add JSON/Text column with default to backfill existing rows
    op.add_column('user', sa.Column('email_prefs', sa.Text(), nullable=False, server_default='{}'))
    # Remove server default afterwards to match model default (application-level)
    try:
        op.alter_column('user', 'email_prefs', server_default=None)
    except Exception:
        # Some dialects may not support dropping server_default this way; ignore
        pass


def downgrade():
    op.drop_column('user', 'email_prefs')
