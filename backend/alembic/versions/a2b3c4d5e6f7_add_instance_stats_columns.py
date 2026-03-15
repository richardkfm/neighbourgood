"""add instance stats columns to known_instances

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-15 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('known_instances', schema=None) as batch_op:
        batch_op.add_column(sa.Column('resource_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('skill_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('event_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('active_user_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('known_instances', schema=None) as batch_op:
        batch_op.drop_column('active_user_count')
        batch_op.drop_column('event_count')
        batch_op.drop_column('skill_count')
        batch_op.drop_column('resource_count')
