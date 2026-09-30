"""mesh message signing keys, per-author mesh dedup, ticket client_id, alert expiry

- mesh_device_keys: ECDSA P-256 public keys per user and device (revocable)
- mesh_synced_messages: author_id + verified; the mesh message ID is unique per
  author instead of globally (nobody can squat another author's message ID)
- emergency_tickets.client_id: idempotency key shared by REST create and mesh,
  unique per author
- red_sky_alerts.expires_at / sent_red_sky_alerts.expires_at

Revision ID: f3a4b5c6d7e8
Revises: e8f9a0b1c2d3
Create Date: 2026-09-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'mesh_device_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('key_id', sa.String(length=64), nullable=False),
        sa.Column('public_key', sa.String(length=200), nullable=False),
        sa.Column('device_name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('mesh_device_keys', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mesh_device_keys_key_id'), ['key_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_mesh_device_keys_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('mesh_synced_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('author_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('verified', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.create_foreign_key('fk_mesh_synced_messages_author_id_users', 'users', ['author_id'], ['id'])
        batch_op.create_index(batch_op.f('ix_mesh_synced_messages_author_id'), ['author_id'], unique=False)
    # Existing rows were all attributed to whoever synced them
    op.execute('UPDATE mesh_synced_messages SET author_id = synced_by_id WHERE author_id IS NULL')
    with op.batch_alter_table('mesh_synced_messages', schema=None) as batch_op:
        batch_op.drop_index('ix_mesh_synced_messages_mesh_message_id')
        batch_op.create_index('ix_mesh_synced_messages_mesh_message_id', ['mesh_message_id'], unique=False)
        batch_op.create_unique_constraint('uq_mesh_synced_message_author', ['mesh_message_id', 'author_id'])

    with op.batch_alter_table('emergency_tickets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('client_id', sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint('uq_emergency_ticket_author_client_id', ['author_id', 'client_id'])

    with op.batch_alter_table('red_sky_alerts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expires_at', sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f('ix_red_sky_alerts_expires_at'), ['expires_at'], unique=False)

    with op.batch_alter_table('sent_red_sky_alerts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('sent_red_sky_alerts', schema=None) as batch_op:
        batch_op.drop_column('expires_at')

    with op.batch_alter_table('red_sky_alerts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_red_sky_alerts_expires_at'))
        batch_op.drop_column('expires_at')

    with op.batch_alter_table('emergency_tickets', schema=None) as batch_op:
        batch_op.drop_constraint('uq_emergency_ticket_author_client_id', type_='unique')
        batch_op.drop_column('client_id')

    # Restoring global uniqueness: keep the earliest row per mesh message ID
    op.execute(
        'DELETE FROM mesh_synced_messages WHERE id NOT IN '
        '(SELECT MIN(id) FROM mesh_synced_messages GROUP BY mesh_message_id)'
    )
    with op.batch_alter_table('mesh_synced_messages', schema=None) as batch_op:
        batch_op.drop_constraint('uq_mesh_synced_message_author', type_='unique')
        batch_op.drop_index('ix_mesh_synced_messages_mesh_message_id')
        batch_op.create_index('ix_mesh_synced_messages_mesh_message_id', ['mesh_message_id'], unique=True)
        batch_op.drop_index(batch_op.f('ix_mesh_synced_messages_author_id'))
        batch_op.drop_constraint('fk_mesh_synced_messages_author_id_users', type_='foreignkey')
        batch_op.drop_column('verified')
        batch_op.drop_column('author_id')

    with op.batch_alter_table('mesh_device_keys', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mesh_device_keys_user_id'))
        batch_op.drop_index(batch_op.f('ix_mesh_device_keys_key_id'))

    op.drop_table('mesh_device_keys')
