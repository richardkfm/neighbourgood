"""add users.token_version and resources/skills.imported

token_version lets a password/email change invalidate every previously issued
JWT. imported marks listings created through /federation/migrate/import so they
can be excluded from reputation scoring.

Revision ID: f2a3b4c5d6e7
Revises: e8f9a0b1c2d3
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('token_version', sa.Integer(), server_default='0', nullable=False))
    with op.batch_alter_table('resources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('imported', sa.Boolean(), server_default=sa.false(), nullable=False))
    with op.batch_alter_table('skills', schema=None) as batch_op:
        batch_op.add_column(sa.Column('imported', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('skills', schema=None) as batch_op:
        batch_op.drop_column('imported')
    with op.batch_alter_table('resources', schema=None) as batch_op:
        batch_op.drop_column('imported')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('token_version')
