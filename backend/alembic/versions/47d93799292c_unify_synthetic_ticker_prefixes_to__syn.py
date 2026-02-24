"""unify synthetic ticker prefixes to _SYN

Revision ID: 47d93799292c
Revises: f9b3df5f0ef2
Create Date: 2026-02-23 20:07:36.491854

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '47d93799292c'
down_revision: Union[str, Sequence[str], None] = 'f9b3df5f0ef2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Old prefixes and their lengths (for SUBSTR offset, 1-based)
_OLD_PREFIXES = [
    ("_SF:", 5),       # len("_SF:") + 1
    ("_PLAID:", 8),    # len("_PLAID:") + 1
    ("_MAN:", 6),      # len("_MAN:") + 1
]

_TABLES_WITH_TICKER = ["securities", "holdings", "daily_holding_values", "holding_lots"]


def upgrade() -> None:
    """Rewrite _SF:, _PLAID:, and _MAN: prefixes to _SYN: in all ticker columns."""
    for prefix, substr_start in _OLD_PREFIXES:
        for table in _TABLES_WITH_TICKER:
            op.execute(
                f"UPDATE {table} "
                f"SET ticker = '_SYN:' || SUBSTR(ticker, {substr_start}) "
                f"WHERE ticker LIKE '{prefix}%'"
            )


def downgrade() -> None:
    """Reverse is not possible — we no longer know which prefix was original."""
    pass
