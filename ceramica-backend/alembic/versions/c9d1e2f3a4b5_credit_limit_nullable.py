"""credit_limit_cents nullable (null=unlimited, 0=no credit)

Revision ID: c9d1e2f3a4b5
Revises: a1b2c3d4e5f6
Create Date: 2026-10-19 06:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c9d1e2f3a4b5'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('clients') as batch_op:
        batch_op.alter_column('credit_limit_cents', nullable=True, server_default='0')


def downgrade() -> None:
    with op.batch_alter_table('clients') as batch_op:
        batch_op.alter_column('credit_limit_cents', nullable=False, server_default='0')
