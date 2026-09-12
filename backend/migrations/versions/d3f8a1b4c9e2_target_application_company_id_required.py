"""target application company_id required

Revision ID: d3f8a1b4c9e2
Revises: 8af704ff2136
Create Date: 2026-09-12 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3f8a1b4c9e2'
down_revision: Union[str, None] = '8af704ff2136'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Les applications mail existantes n'avaient pas d'entreprise rattachée (ancien
    # comportement, canal volontairement partagé) — rattachées à la première entreprise
    # avant de poser la contrainte NOT NULL, faute de mieux : `company_id` devient
    # obligatoire pour que RoutingRuleService.resolve puisse filtrer les applications
    # mail par entreprise réceptrice comme il le fait déjà pour afnor_api (§ NF2).
    op.execute(
        """
        UPDATE target_applications
        SET company_id = (SELECT id FROM companies ORDER BY id LIMIT 1)
        WHERE company_id IS NULL
        """
    )
    with op.batch_alter_table('target_applications') as batch_op:
        batch_op.alter_column('company_id', existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('target_applications') as batch_op:
        batch_op.alter_column('company_id', existing_type=sa.Integer(), nullable=True)
