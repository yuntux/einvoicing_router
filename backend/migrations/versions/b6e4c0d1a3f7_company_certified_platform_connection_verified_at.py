"""company certified_platform_connection_verified_at

Revision ID: b6e4c0d1a3f7
Revises: f3a8c1d5b6e2
Create Date: 2026-09-13 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6e4c0d1a3f7'
down_revision: Union[str, None] = 'f3a8c1d5b6e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('companies') as batch_op:
        batch_op.add_column(sa.Column('certified_platform_connection_verified_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('companies') as batch_op:
        batch_op.drop_column('certified_platform_connection_verified_at')
