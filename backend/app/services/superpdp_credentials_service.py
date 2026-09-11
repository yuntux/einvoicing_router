"""Identifiants OAuth2 que SuperPDP fournit au routeur, par entreprise gérée
(spec.md § 4.10, scope `router_to_superpdp`, lot 6) — distincts des applications OAuth
que le routeur émet lui-même pour ses consommateurs (§ 4.9.2, scope `consumer_to_router`,
lot 4)."""

from sqlalchemy.orm import Session

from app.models.referential import OAuthAppType, OAuthApplication, OAuthScope
from app.services.secrets_encryption import decrypt_secret, encrypt_secret


def get_credentials_application(db: Session, *, company_id: int) -> OAuthApplication | None:
    return (
        db.query(OAuthApplication)
        .filter(
            OAuthApplication.company_id == company_id,
            OAuthApplication.scope == OAuthScope.ROUTER_TO_SUPERPDP,
        )
        .first()
    )


def set_credentials(
    db: Session, *, company_id: int, client_id: str, client_secret: str
) -> OAuthApplication:
    """Enregistre (ou remplace) les identifiants fournis par SuperPDP pour cette
    entreprise. Le secret n'est jamais journalisé ni renvoyé en clair ensuite."""
    application = get_credentials_application(db, company_id=company_id)
    if application is None:
        application = OAuthApplication(
            company_id=company_id,
            app_type=OAuthAppType.CONFIDENTIAL,
            scope=OAuthScope.ROUTER_TO_SUPERPDP,
        )
        db.add(application)

    application.client_id = client_id
    application.client_secret_encrypted = encrypt_secret(client_secret)
    # Un changement d'identifiants invalide le jeton précédemment mis en cache.
    application.token_cache = None
    db.commit()
    db.refresh(application)
    return application


def get_decrypted_secret(application: OAuthApplication) -> str:
    if not application.client_secret_encrypted:
        raise ValueError(
            f"Aucun secret SuperPDP enregistré pour l'application {application.id}."
        )
    return decrypt_secret(application.client_secret_encrypted)
