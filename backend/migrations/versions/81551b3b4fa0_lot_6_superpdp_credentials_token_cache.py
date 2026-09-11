"""lot 6: superpdp credentials, token cache

Revision ID: 81551b3b4fa0
Revises: 39900f23b9ae
Create Date: 2026-09-11 17:19:05.729779

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '81551b3b4fa0'
down_revision: Union[str, None] = '39900f23b9ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite ne supporte pas ALTER TABLE ... ALTER COLUMN : mode batch (copy-and-move).
    with op.batch_alter_table('oauth_applications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('client_secret_encrypted', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('token_cache', sa.Text(), nullable=True))
        batch_op.alter_column(
            'client_secret_hash', existing_type=sa.VARCHAR(length=255), nullable=True
        )


def downgrade() -> None:
    with op.batch_alter_table('oauth_applications', schema=None) as batch_op:
        batch_op.alter_column(
            'client_secret_hash', existing_type=sa.VARCHAR(length=255), nullable=False
        )
        batch_op.drop_column('token_cache')
        batch_op.drop_column('client_secret_encrypted')
