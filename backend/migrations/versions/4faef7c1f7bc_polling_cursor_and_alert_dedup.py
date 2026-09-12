"""company last_polled_at + invoice unrouted_alert_sent

Revision ID: 4faef7c1f7bc
Revises: b4c8e21f7a56
Create Date: 2026-09-12 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4faef7c1f7bc'
down_revision: Union[str, None] = 'b4c8e21f7a56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('companies') as batch_op:
        batch_op.add_column(sa.Column('last_polled_at', sa.DateTime(), nullable=True))
    with op.batch_alter_table('invoices') as batch_op:
        batch_op.add_column(
            sa.Column(
                'unrouted_alert_sent', sa.Boolean(), nullable=False, server_default='0'
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('invoices') as batch_op:
        batch_op.drop_column('unrouted_alert_sent')
    with op.batch_alter_table('companies') as batch_op:
        batch_op.drop_column('last_polled_at')
