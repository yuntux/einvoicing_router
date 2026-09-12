"""flow trace request/response headers

Revision ID: b4c8e21f7a56
Revises: ffe76f00e0c7
Create Date: 2026-09-12 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c8e21f7a56'
down_revision: Union[str, None] = 'ffe76f00e0c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('flow_traces') as batch_op:
        batch_op.add_column(sa.Column('request_headers', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('response_headers', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('flow_traces') as batch_op:
        batch_op.drop_column('response_headers')
        batch_op.drop_column('request_headers')
