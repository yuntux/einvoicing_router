"""audit columns create_user_id create_datetime write_user_id write_datetime

Revision ID: 1f7c5049c13f
Revises: a71c2e9f6b3d
Create Date: 2026-09-12 04:14:13.278482

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f7c5049c13f'
down_revision: Union[str, None] = 'a71c2e9f6b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    "companies",
    "partner_directories",
    "target_applications",
    "routing_rules",
    "oauth_applications",
    "users",
    "router_settings",
    "billing_manager_contacts",
]


def upgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("create_user_id", sa.Integer(), nullable=True))
            batch_op.add_column(
                sa.Column(
                    "create_datetime",
                    sa.DateTime(),
                    nullable=False,
                    server_default=sa.func.now(),
                )
            )
            batch_op.add_column(sa.Column("write_user_id", sa.Integer(), nullable=True))
            batch_op.add_column(
                sa.Column(
                    "write_datetime",
                    sa.DateTime(),
                    nullable=False,
                    server_default=sa.func.now(),
                )
            )
            batch_op.create_foreign_key(
                f"fk_{table}_create_user_id_users", "users", ["create_user_id"], ["id"]
            )
            batch_op.create_foreign_key(
                f"fk_{table}_write_user_id_users", "users", ["write_user_id"], ["id"]
            )


def downgrade() -> None:
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(f"fk_{table}_write_user_id_users", type_="foreignkey")
            batch_op.drop_constraint(f"fk_{table}_create_user_id_users", type_="foreignkey")
            batch_op.drop_column("write_datetime")
            batch_op.drop_column("write_user_id")
            batch_op.drop_column("create_datetime")
            batch_op.drop_column("create_user_id")
