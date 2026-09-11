"""user pre-provisioning: is_active, nullable name

Revision ID: 26574bbf0754
Revises: e6c2d757f43b
Create Date: 2026-09-11 20:47:19.800835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '26574bbf0754'
down_revision: Union[str, None] = 'e6c2d757f43b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite ne supporte pas ALTER COLUMN directement (§ NF5) : batch mode requis
    # (recrée la table sous le capot), cf. adjustement manuel de l'autogénération.
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False))
        batch_op.alter_column('name', existing_type=sa.VARCHAR(length=255), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('name', existing_type=sa.VARCHAR(length=255), nullable=False)
        batch_op.drop_column('is_active')
