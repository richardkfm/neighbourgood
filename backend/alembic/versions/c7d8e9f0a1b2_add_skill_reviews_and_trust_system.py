"""add skill reviews and trust system

Revision ID: c7d8e9f0a1b2
Revises: b4c5d6e7f8a9
Create Date: 2026-04-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        # Make booking_id nullable (was non-nullable)
        batch_op.alter_column('booking_id', existing_type=sa.Integer(), nullable=True)
        # Add skill_id FK column
        batch_op.add_column(sa.Column('skill_id', sa.Integer(), sa.ForeignKey('skills.id'), nullable=True))
        batch_op.create_index('ix_reviews_skill_id', ['skill_id'])
        # Add review_type column
        batch_op.add_column(sa.Column('review_type', sa.String(length=10), nullable=False, server_default='booking'))
        batch_op.create_index('ix_reviews_review_type', ['review_type'])
        # Add unique constraint for skill reviews
        batch_op.create_unique_constraint('uq_review_skill_reviewer', ['skill_id', 'reviewer_id'])

    # Backfill existing rows
    op.execute("UPDATE reviews SET review_type = 'booking' WHERE review_type IS NULL OR review_type = ''")


def downgrade() -> None:
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.drop_constraint('uq_review_skill_reviewer', type_='unique')
        batch_op.drop_index('ix_reviews_review_type')
        batch_op.drop_column('review_type')
        batch_op.drop_index('ix_reviews_skill_id')
        batch_op.drop_column('skill_id')
        batch_op.alter_column('booking_id', existing_type=sa.Integer(), nullable=False)
