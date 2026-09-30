"""verify federated Red Sky alerts against their source instance

Adds the sent_red_sky_alerts table (alerts this instance broadcast, which
receivers fetch back to verify) and red_sky_alerts.source_alert_uid (the
alert's ID on its source instance, unique per source).

Revision ID: e8f9a0b1c2d3
Revises: b6cf30bac69d
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'b6cf30bac69d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sent_red_sky_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alert_uid', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('sent_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['sent_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('sent_red_sky_alerts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sent_red_sky_alerts_alert_uid'), ['alert_uid'], unique=True)
        batch_op.create_index(batch_op.f('ix_sent_red_sky_alerts_sent_by_id'), ['sent_by_id'], unique=False)

    with op.batch_alter_table('red_sky_alerts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_alert_uid', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_red_sky_alerts_source_alert_uid'), ['source_alert_uid'], unique=False)
        batch_op.create_unique_constraint('uq_red_sky_alert_source_uid', ['source_instance_url', 'source_alert_uid'])


def downgrade() -> None:
    with op.batch_alter_table('red_sky_alerts', schema=None) as batch_op:
        batch_op.drop_constraint('uq_red_sky_alert_source_uid', type_='unique')
        batch_op.drop_index(batch_op.f('ix_red_sky_alerts_source_alert_uid'))
        batch_op.drop_column('source_alert_uid')

    with op.batch_alter_table('sent_red_sky_alerts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sent_red_sky_alerts_sent_by_id'))
        batch_op.drop_index(batch_op.f('ix_sent_red_sky_alerts_alert_uid'))

    op.drop_table('sent_red_sky_alerts')
