"""routing rule start_date required

Revision ID: a71c2e9f6b3d
Revises: d3f8a1b4c9e2
Create Date: 2026-09-12 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a71c2e9f6b3d'
down_revision: Union[str, None] = 'd3f8a1b4c9e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Une règle sans start_date était jusqu'ici active immédiatement et sans limite
    # dès sa création — aucun moyen de tracer depuis quand elle s'applique. Bornée à
    # la date du jour à défaut de mieux (aucune date de création tracée sur
    # RoutingRule) avant de poser la contrainte NOT NULL.
    op.execute(
        """
        UPDATE routing_rules
        SET start_date = CURRENT_DATE
        WHERE start_date IS NULL
        """
    )
    with op.batch_alter_table('routing_rules') as batch_op:
        batch_op.alter_column('start_date', existing_type=sa.Date(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('routing_rules') as batch_op:
        batch_op.alter_column('start_date', existing_type=sa.Date(), nullable=True)
