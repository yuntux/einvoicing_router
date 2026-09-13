"""company certified_platform_directory_id

Revision ID: a2b7e1f4c8d0
Revises: d1c4a3cc9a41
Create Date: 2026-09-13 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b7e1f4c8d0'
down_revision: Union[str, None] = 'd1c4a3cc9a41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('companies') as batch_op:
        batch_op.add_column(sa.Column('certified_platform_directory_id', sa.String(length=35), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('companies') as batch_op:
        batch_op.drop_column('certified_platform_directory_id')
