"""add error columns to plaid_items

Revision ID: a5718f64895f
Revises: ff6c3c48633e
Create Date: 2026-03-03 20:15:49.870090

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5718f64895f'
down_revision: Union[str, Sequence[str], None] = 'ff6c3c48633e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('plaid_items', sa.Column('error_code', sa.String(), nullable=True))
    op.add_column('plaid_items', sa.Column('error_message', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('plaid_items', 'error_message')
    op.drop_column('plaid_items', 'error_code')
