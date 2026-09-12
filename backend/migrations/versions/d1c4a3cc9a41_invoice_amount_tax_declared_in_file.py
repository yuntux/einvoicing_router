"""invoice amount_tax declared in file

Revision ID: d1c4a3cc9a41
Revises: 5eb84f686d99
Create Date: 2026-09-13 00:28:46.738182

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1c4a3cc9a41'
down_revision: Union[str, None] = '5eb84f686d99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('invoices') as batch_op:
        batch_op.add_column(sa.Column('amount_tax', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('invoices') as batch_op:
        batch_op.drop_column('amount_tax')
