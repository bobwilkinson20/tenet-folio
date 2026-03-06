"""add report_sheet_targets table

Revision ID: 9229a8bf10d3
Revises: a5718f64895f
Create Date: 2026-03-06 11:36:52.767484

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9229a8bf10d3'
down_revision: Union[str, Sequence[str], None] = 'a5718f64895f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('report_sheet_targets',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('report_type', sa.String(), nullable=False),
    sa.Column('spreadsheet_id', sa.String(), nullable=False),
    sa.Column('display_name', sa.String(), nullable=False),
    sa.Column('config', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_report_sheet_targets_report_type', 'report_sheet_targets', ['report_type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_report_sheet_targets_report_type', table_name='report_sheet_targets')
    op.drop_table('report_sheet_targets')
