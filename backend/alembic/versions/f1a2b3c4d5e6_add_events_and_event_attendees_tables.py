"""add events and event_attendees tables

Revision ID: f1a2b3c4d5e6
Revises: d1e2f3a4b5c6
Create Date: 2026-03-13 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('start_at', sa.DateTime(), nullable=False),
        sa.Column('end_at', sa.DateTime(), nullable=True),
        sa.Column('location', sa.String(300), nullable=True),
        sa.Column('max_attendees', sa.Integer(), nullable=True),
        sa.Column('organizer_id', sa.Integer(), nullable=False),
        sa.Column('community_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['community_id'], ['communities.id']),
        sa.ForeignKeyConstraint(['organizer_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_events_category'), ['category'], unique=False)
        batch_op.create_index(batch_op.f('ix_events_community_id'), ['community_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_events_organizer_id'), ['organizer_id'], unique=False)

    op.create_table(
        'event_attendees',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('joined_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'user_id', name='uq_event_attendee'),
    )
    with op.batch_alter_table('event_attendees', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_event_attendees_event_id'), ['event_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_event_attendees_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('event_attendees', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_event_attendees_user_id'))
        batch_op.drop_index(batch_op.f('ix_event_attendees_event_id'))
    op.drop_table('event_attendees')

    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_events_organizer_id'))
        batch_op.drop_index(batch_op.f('ix_events_community_id'))
        batch_op.drop_index(batch_op.f('ix_events_category'))
    op.drop_table('events')
