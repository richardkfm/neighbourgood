"""merge account features (password reset) and security (token_version) heads

Revision ID: b8d9e0f1a2b3
Revises: a7c1d3e5f901, f2a3b4c5d6e7
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'b8d9e0f1a2b3'
down_revision: Union[str, Sequence[str], None] = ('a7c1d3e5f901', 'f2a3b4c5d6e7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
