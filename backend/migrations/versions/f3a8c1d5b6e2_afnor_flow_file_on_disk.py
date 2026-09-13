"""afnor_flows.file_bin -> file_path (uniformise le stockage des flux CDAR sur
disque, comme Invoice.file_path et LifecycleEventAttachment.file_path, au lieu
d'un BLOB en base)

Revision ID: f3a8c1d5b6e2
Revises: a2b7e1f4c8d0
Create Date: 2026-09-13 14:00:00.000000

"""
import os
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a8c1d5b6e2'
down_revision: Union[str, None] = 'a2b7e1f4c8d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _storage_root() -> Path:
    # Même variable d'environnement/valeur par défaut que `app.config.Settings.
    # invoice_storage_root` (`ROUTER_` + `INVOICE_STORAGE_ROOT`) — pas d'import de
    # `app.config` ici pour ne pas faire dépendre une migration de la validation
    # Pydantic complète des settings applicatives.
    return Path(os.environ.get("ROUTER_INVOICE_STORAGE_ROOT", "./data/invoices"))


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table('afnor_flows') as batch_op:
        batch_op.add_column(sa.Column('file_path', sa.String(length=1000), nullable=True))

    root = _storage_root()
    rows = bind.execute(
        sa.text(
            """
            SELECT af.id, af.file_bin, c.siren
            FROM afnor_flows af
            JOIN invoices i ON i.id = af.invoice_id
            JOIN companies c ON c.id = i.company_id
            WHERE af.file_bin IS NOT NULL
            """
        )
    ).fetchall()
    for flow_id, file_bin, siren in rows:
        directory = root / siren / "afnor-flows" / str(flow_id)
        directory.mkdir(parents=True, exist_ok=True)
        file_path = directory / "cdar.xml"
        file_path.write_bytes(file_bin)
        bind.execute(
            sa.text("UPDATE afnor_flows SET file_path = :file_path WHERE id = :id"),
            {"file_path": str(file_path), "id": flow_id},
        )

    with op.batch_alter_table('afnor_flows') as batch_op:
        batch_op.drop_column('file_bin')


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table('afnor_flows') as batch_op:
        batch_op.add_column(sa.Column('file_bin', sa.LargeBinary(), nullable=True))

    rows = bind.execute(
        sa.text("SELECT id, file_path FROM afnor_flows WHERE file_path IS NOT NULL")
    ).fetchall()
    for flow_id, file_path in rows:
        path = Path(file_path)
        if path.exists():
            bind.execute(
                sa.text("UPDATE afnor_flows SET file_bin = :file_bin WHERE id = :id"),
                {"file_bin": path.read_bytes(), "id": flow_id},
            )

    with op.batch_alter_table('afnor_flows') as batch_op:
        batch_op.drop_column('file_path')
