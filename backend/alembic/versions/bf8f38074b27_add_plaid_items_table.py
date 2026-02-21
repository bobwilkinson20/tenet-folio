"""add plaid_items table

Revision ID: bf8f38074b27
Revises: 44b30f32f373
Create Date: 2026-02-21 09:22:39.929407

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf8f38074b27'
down_revision: Union[str, Sequence[str], None] = '44b30f32f373'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('plaid_items',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('item_id', sa.String(), nullable=False),
    sa.Column('access_token', sa.String(), nullable=False),
    sa.Column('institution_id', sa.String(), nullable=True),
    sa.Column('institution_name', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_plaid_items_item_id'), 'plaid_items', ['item_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_plaid_items_item_id'), table_name='plaid_items')
    op.drop_table('plaid_items')
