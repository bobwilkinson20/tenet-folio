"""add price_date to daily_holding_values

Revision ID: a1b2c3d4e5f6
Revises: 47d93799292c
Create Date: 2026-02-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '47d93799292c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable price_date column to daily_holding_values."""
    from sqlalchemy import inspect as sa_inspect
    conn = op.get_bind()
    existing = [c['name'] for c in sa_inspect(conn).get_columns('daily_holding_values')]

    if 'price_date' not in existing:
        op.add_column('daily_holding_values', sa.Column('price_date', sa.Date(), nullable=True))


def downgrade() -> None:
    """Remove price_date column from daily_holding_values."""
    from sqlalchemy import inspect as sa_inspect
    conn = op.get_bind()
    existing = [c['name'] for c in sa_inspect(conn).get_columns('daily_holding_values')]
    if 'price_date' in existing:
        op.drop_column('daily_holding_values', 'price_date')
