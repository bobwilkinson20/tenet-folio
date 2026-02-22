"""add account deactivation fields

Revision ID: f9b3df5f0ef2
Revises: bf8f38074b27
Create Date: 2026-02-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9b3df5f0ef2'
down_revision: Union[str, Sequence[str], None] = 'bf8f38074b27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy import inspect as sa_inspect
    conn = op.get_bind()
    existing = [c['name'] for c in sa_inspect(conn).get_columns('accounts')]

    if 'deactivated_at' not in existing:
        op.add_column('accounts', sa.Column('deactivated_at', sa.DateTime(), nullable=True))
    if 'superseded_by_account_id' not in existing:
        op.add_column('accounts', sa.Column('superseded_by_account_id', sa.String(length=36), nullable=True))
    # Note: SQLite does not support adding FK constraints via ALTER TABLE.
    # The FK relationship is enforced at the ORM layer; the column is a plain
    # String(36) referencing accounts.id in practice.


def downgrade() -> None:
    """Downgrade schema."""
    from sqlalchemy import inspect as sa_inspect
    conn = op.get_bind()
    existing = [c['name'] for c in sa_inspect(conn).get_columns('accounts')]
    if 'superseded_by_account_id' in existing:
        op.drop_column('accounts', 'superseded_by_account_id')
    if 'deactivated_at' in existing:
        op.drop_column('accounts', 'deactivated_at')
