"""oauth application platform (replaces endpoint_url)

Revision ID: 8af704ff2136
Revises: c17df992a521
Create Date: 2026-09-12 01:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8af704ff2136'
down_revision: Union[str, None] = 'c17df992a521'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('oauth_applications') as batch_op:
        batch_op.drop_column('endpoint_url')
        batch_op.add_column(sa.Column('platform', sa.String(length=50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('oauth_applications') as batch_op:
        batch_op.drop_column('platform')
        batch_op.add_column(sa.Column('endpoint_url', sa.String(length=500), nullable=True))
