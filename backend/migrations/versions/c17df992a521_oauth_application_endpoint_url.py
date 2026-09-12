"""oauth application endpoint_url

Revision ID: c17df992a521
Revises: 57b21385ef0b
Create Date: 2026-09-12 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c17df992a521'
down_revision: Union[str, None] = '57b21385ef0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('oauth_applications', sa.Column('endpoint_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('oauth_applications', 'endpoint_url')
