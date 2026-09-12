"""drop oauth_applications table

Modèle précédent : une table `oauth_applications` unique gérant deux scopes aux
colonnes disjointes selon le scope (`router_to_superpdp` vs `consumer_to_router`) —
source de confusion (colonnes toujours à moitié NULL selon le scope de la ligne).

Nouveau modèle :
- `router_to_superpdp` (identifiants que SuperPDP fournit AU ROUTEUR, un jeu par
  entreprise) : porté directement par de nouvelles colonnes `Company.superpdp_*`.
- `consumer_to_router` (identifiants que le routeur ÉMET pour un consommateur comme
  Odoo, un jeu par `TargetApplication` de méthode `afnor_api`) : fusionné dans le
  JSON `TargetApplication.parameters`, la même colonne qui porte déjà les paramètres
  de la méthode `mail` (to/cc/bcc) — ces identifiants ne sont jamais qu'une variante
  des "paramètres de la méthode de routage", pas une entité indépendante.

Revision ID: ab9e74c72f29
Revises: af5ed0c53e72
Create Date: 2026-09-12 00:00:00.000000

"""

import json

from alembic import op
import sqlalchemy as sa

revision = "ab9e74c72f29"
down_revision = "af5ed0c53e72"
branch_labels = None
depends_on = None


def _as_dict(value) -> dict:
    if value is None:
        return {}
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def upgrade() -> None:
    with op.batch_alter_table("companies") as batch_op:
        batch_op.add_column(sa.Column("superpdp_client_id", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("superpdp_client_secret_encrypted", sa.Text(), nullable=True)
        )
        batch_op.add_column(sa.Column("superpdp_token_cache", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("superpdp_platform", sa.String(length=50), nullable=True))

    conn = op.get_bind()
    metadata = sa.MetaData()
    oauth_applications = sa.Table("oauth_applications", metadata, autoload_with=conn)
    companies = sa.Table("companies", metadata, autoload_with=conn)
    target_applications = sa.Table("target_applications", metadata, autoload_with=conn)

    for row in conn.execute(
        sa.select(oauth_applications).where(oauth_applications.c.scope == "router_to_superpdp")
    ):
        conn.execute(
            sa.update(companies)
            .where(companies.c.id == row.company_id)
            .values(
                superpdp_client_id=row.client_id,
                superpdp_client_secret_encrypted=row.client_secret_encrypted,
                superpdp_token_cache=row.token_cache,
                superpdp_platform=row.platform,
            )
        )

    for row in conn.execute(
        sa.select(oauth_applications).where(oauth_applications.c.scope == "consumer_to_router")
    ):
        target_row = conn.execute(
            sa.select(target_applications).where(
                target_applications.c.oauth_application_id == row.id
            )
        ).first()
        if target_row is None:
            # Ligne orpheline (aucune TargetApplication ne la référence) : rien à
            # fusionner, elle disparaît simplement avec la table.
            continue
        merged = {
            **_as_dict(target_row.parameters),
            "client_id": row.client_id,
            "client_secret_hash": row.client_secret_hash,
            "app_type": row.app_type,
            "redirect_urls": row.redirect_urls,
            "preferred_conversion_format": row.preferred_conversion_format,
            "webhook_url": row.webhook_url,
        }
        conn.execute(
            sa.update(target_applications)
            .where(target_applications.c.id == target_row.id)
            .values(parameters=merged)
        )

    with op.batch_alter_table("target_applications") as batch_op:
        batch_op.drop_column("oauth_application_id")

    op.drop_table("oauth_applications")


def downgrade() -> None:
    """Best-effort : reconstruit `oauth_applications` à partir de `Company.superpdp_*`
    et de `TargetApplication.parameters` — suffisant pour ne pas perdre les données
    (identifiants, hash, config), mais les `id` d'origine de `oauth_applications` ne
    sont pas préservés (nouvelle auto-incrémentation)."""
    op.create_table(
        "oauth_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("client_id", sa.String(length=64), unique=True, index=True, nullable=False),
        sa.Column("client_secret_hash", sa.String(length=255), nullable=True),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("token_cache", sa.Text(), nullable=True),
        sa.Column("app_type", sa.String(length=20), nullable=False),
        sa.Column("scope", sa.String(length=30), nullable=False),
        sa.Column("redirect_urls", sa.String(length=2000), nullable=True),
        sa.Column("preferred_conversion_format", sa.String(length=50), nullable=True),
        sa.Column("afnor_api_version", sa.String(length=10), nullable=True),
        sa.Column("webhook_url", sa.String(length=500), nullable=True),
        sa.Column("platform", sa.String(length=50), nullable=True),
        sa.Column("create_user_id", sa.Integer(), nullable=True),
        sa.Column("create_datetime", sa.DateTime(), nullable=False),
        sa.Column("write_user_id", sa.Integer(), nullable=True),
        sa.Column("write_datetime", sa.DateTime(), nullable=False),
    )
    with op.batch_alter_table("target_applications") as batch_op:
        batch_op.add_column(sa.Column("oauth_application_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_target_applications_oauth_application_id_oauth_applications",
            "oauth_applications",
            ["oauth_application_id"],
            ["id"],
        )

    conn = op.get_bind()
    metadata = sa.MetaData()
    companies = sa.Table("companies", metadata, autoload_with=conn)
    target_applications = sa.Table("target_applications", metadata, autoload_with=conn)
    oauth_applications = sa.Table("oauth_applications", metadata, autoload_with=conn)

    now = sa.func.now()

    for row in conn.execute(
        sa.select(companies).where(companies.c.superpdp_client_id.is_not(None))
    ):
        conn.execute(
            sa.insert(oauth_applications).values(
                company_id=row.id,
                client_id=row.superpdp_client_id,
                client_secret_encrypted=row.superpdp_client_secret_encrypted,
                token_cache=row.superpdp_token_cache,
                platform=row.superpdp_platform,
                app_type="confidential",
                scope="router_to_superpdp",
                create_datetime=now,
                write_datetime=now,
            )
        )

    for row in conn.execute(
        sa.select(target_applications).where(target_applications.c.routing_method == "afnor_api")
    ):
        params = _as_dict(row.parameters)
        if not params.get("client_id"):
            continue
        result = conn.execute(
            sa.insert(oauth_applications).values(
                company_id=row.company_id,
                client_id=params.get("client_id"),
                client_secret_hash=params.get("client_secret_hash"),
                app_type=params.get("app_type") or "confidential",
                scope="consumer_to_router",
                redirect_urls=params.get("redirect_urls"),
                preferred_conversion_format=params.get("preferred_conversion_format"),
                webhook_url=params.get("webhook_url"),
                create_datetime=now,
                write_datetime=now,
            )
        )
        conn.execute(
            sa.update(target_applications)
            .where(target_applications.c.id == row.id)
            .values(oauth_application_id=result.inserted_primary_key[0])
        )

    with op.batch_alter_table("companies") as batch_op:
        batch_op.drop_column("superpdp_platform")
        batch_op.drop_column("superpdp_token_cache")
        batch_op.drop_column("superpdp_client_secret_encrypted")
        batch_op.drop_column("superpdp_client_id")
