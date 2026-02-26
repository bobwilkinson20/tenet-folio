"""add price_source to daily_holding_values

Revision ID: ff6c3c48633e
Revises: 6302481a7f95
Create Date: 2026-02-25 15:42:04.800336

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff6c3c48633e'
down_revision: Union[str, Sequence[str], None] = '6302481a7f95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable price_source column to daily_holding_values."""
    op.add_column('daily_holding_values', sa.Column('price_source', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Remove price_source column from daily_holding_values."""
    op.drop_column('daily_holding_values', 'price_source')
