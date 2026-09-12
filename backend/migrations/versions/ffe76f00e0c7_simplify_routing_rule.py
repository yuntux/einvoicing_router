"""simplify routing rule: drop start_date/end_date/active, add unique(partner, target)

Revision ID: ffe76f00e0c7
Revises: 1f7c5049c13f
Create Date: 2026-09-12 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ffe76f00e0c7'
down_revision: Union[str, None] = '1f7c5049c13f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('routing_rules') as batch_op:
        batch_op.drop_column('start_date')
        batch_op.drop_column('end_date')
        batch_op.drop_column('active')
        batch_op.create_unique_constraint(
            'uq_routing_rule_partner_target', ['partner_directory_id', 'target_application_id']
        )


def downgrade() -> None:
    with op.batch_alter_table('routing_rules') as batch_op:
        batch_op.drop_constraint('uq_routing_rule_partner_target', type_='unique')
        batch_op.add_column(sa.Column('active', sa.Boolean(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('end_date', sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column('start_date', sa.Date(), nullable=False, server_default='2026-01-01')
        )
