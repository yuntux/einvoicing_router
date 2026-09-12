"""rename superpdp columns to certified platform

Vocabulaire de code interne uniquement (§ demande produit) : "SuperPDP" reste le nom
du vrai partenaire PDP certifié dans le narratif métier (spec.md), les contrats
OpenAPI tiers et les valeurs normatives AFNOR déjà persistées (ex. `FlowTrace.
direction`, `MDT-73`) — ce renommage ne touche que les colonnes qui désignaient ce
concept générique côté routeur.

Revision ID: 5eb84f686d99
Revises: ab9e74c72f29
Create Date: 2026-09-12 16:11:27.217566

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5eb84f686d99'
down_revision: Union[str, None] = 'ab9e74c72f29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('companies') as batch_op:
        batch_op.alter_column('superpdp_client_id', new_column_name='certified_platform_client_id')
        batch_op.alter_column(
            'superpdp_client_secret_encrypted',
            new_column_name='certified_platform_client_secret_encrypted',
        )
        batch_op.alter_column('superpdp_token_cache', new_column_name='certified_platform_token_cache')
        batch_op.alter_column('superpdp_platform', new_column_name='certified_platform')

    with op.batch_alter_table('invoices') as batch_op:
        batch_op.alter_column('superpdp_flow_id', new_column_name='certified_platform_flow_id')
        batch_op.alter_column(
            'superpdp_submitted_at', new_column_name='certified_platform_submitted_at'
        )
        batch_op.alter_column('superpdp_updated_at', new_column_name='certified_platform_updated_at')

    # Renomme aussi l'index lui-même (le batch ci-dessus ne fait que le recréer tel
    # quel sur la colonne renommée, sans changer son nom).
    op.drop_index('ix_invoices_superpdp_flow_id', table_name='invoices')
    op.create_index(
        'ix_invoices_certified_platform_flow_id', 'invoices', ['certified_platform_flow_id']
    )


def downgrade() -> None:
    op.drop_index('ix_invoices_certified_platform_flow_id', table_name='invoices')

    with op.batch_alter_table('invoices') as batch_op:
        batch_op.alter_column('certified_platform_updated_at', new_column_name='superpdp_updated_at')
        batch_op.alter_column(
            'certified_platform_submitted_at', new_column_name='superpdp_submitted_at'
        )
        batch_op.alter_column('certified_platform_flow_id', new_column_name='superpdp_flow_id')

    op.create_index('ix_invoices_superpdp_flow_id', 'invoices', ['superpdp_flow_id'])

    with op.batch_alter_table('companies') as batch_op:
        batch_op.alter_column('certified_platform', new_column_name='superpdp_platform')
        batch_op.alter_column('certified_platform_token_cache', new_column_name='superpdp_token_cache')
        batch_op.alter_column(
            'certified_platform_client_secret_encrypted',
            new_column_name='superpdp_client_secret_encrypted',
        )
        batch_op.alter_column('certified_platform_client_id', new_column_name='superpdp_client_id')
