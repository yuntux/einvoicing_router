"""invoice flow envelope fields

Revision ID: af5ed0c53e72
Revises: 4faef7c1f7bc
Create Date: 2026-09-12 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "af5ed0c53e72"
down_revision = "4faef7c1f7bc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.add_column(sa.Column("flow_profile", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("processing_rule_source", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("tracking_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("flow_direction", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("flow_type", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("flow_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("ack_status", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("ack_details", sa.String(length=2000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.drop_column("ack_details")
        batch_op.drop_column("ack_status")
        batch_op.drop_column("flow_name")
        batch_op.drop_column("flow_type")
        batch_op.drop_column("flow_direction")
        batch_op.drop_column("tracking_id")
        batch_op.drop_column("processing_rule_source")
        batch_op.drop_column("flow_profile")
