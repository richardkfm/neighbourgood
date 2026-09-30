"""merge mesh signing keys / alert expiry head with the account and security heads

Revision ID: c0d1e2f3a4b5
Revises: b8d9e0f1a2b3, f3a4b5c6d7e8
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'c0d1e2f3a4b5'
down_revision: Union[str, Sequence[str], None] = ('b8d9e0f1a2b3', 'f3a4b5c6d7e8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
