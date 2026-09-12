"""Identifiants OAuth2 que SuperPDP fournit au routeur, par entreprise gérée
(spec.md § 4.10, scope `router_to_superpdp`, lot 6) — distincts des applications OAuth
que le routeur émet lui-même pour ses consommateurs (§ 4.9.2, scope `consumer_to_router`,
lot 4)."""

from pyfrctc import pyfrctc as core
from pyfrctc.pyfrctc import PLATFORMS
from sqlalchemy.orm import Session

from app.config import settings
from app.models.referential import OAuthAppType, OAuthApplication, OAuthScope
from app.services.secrets_encryption import decrypt_secret, encrypt_secret


def list_platforms() -> list[dict[str, str]]:
    return [{"key": key, "label": value["label"]} for key, value in PLATFORMS.items()]


def test_connection(
    *, company_siren: str, client_id: str, client_secret: str, platform: str | None
) -> tuple[bool, str | None]:
    """Vérifie que ces identifiants permettent bien d'obtenir un jeton OAuth2 auprès
    de la plateforme AFNOR choisie (§ 4.10) — un aller-retour réseau réel, sans lire
    ni écrire de jeton en cache. Toujours OK en mode `fake` (dev/tests, § 10.1) : rien
    à joindre. Renvoie `(ok, message_erreur)`."""
    resolved_platform = platform or settings.superpdp_platform
    if resolved_platform not in PLATFORMS:
        return False, f"Plateforme AFNOR inconnue : {resolved_platform!r}"

    if settings.superpdp_client_mode == "fake":
        return True, None

    try:
        core.get_session(
            platform=resolved_platform,
            auth_method="client_credentials",
            company_ident4log=company_siren,
            get_token_method=lambda grant_type: {"access_token": None, "expires_at": None},
            update_token_method=lambda token: None,
            client_id=client_id,
            client_secret=client_secret,
        )
    except Exception as exc:  # noqa: BLE001 — connectivité/identifiants tiers, cause imprévisible
        return False, str(exc)
    return True, None


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
    db: Session,
    *,
    company_id: int,
    client_id: str,
    client_secret: str,
    platform: str | None = None,
    actor_user_id: int | None = None,
) -> OAuthApplication:
    """Enregistre (ou remplace) les identifiants fournis par SuperPDP pour cette
    entreprise. Le secret n'est jamais journalisé ni renvoyé en clair ensuite.
    `platform` : `None`/vide = plateforme par défaut du serveur (`settings.
    superpdp_platform`), sinon une clé de `pyfrctc.pyfrctc.PLATFORMS` (§ 4.10).
    `actor_user_id` : utilisateur à l'origine de l'appel (§ NF9), pour
    `create_user_id`/`write_user_id` (`AuditColumnsMixin`)."""
    if platform and platform not in PLATFORMS:
        raise ValueError(f"Plateforme AFNOR inconnue : {platform!r}")

    application = get_credentials_application(db, company_id=company_id)
    if application is None:
        application = OAuthApplication(
            company_id=company_id,
            app_type=OAuthAppType.CONFIDENTIAL,
            scope=OAuthScope.ROUTER_TO_SUPERPDP,
            create_user_id=actor_user_id,
        )
        db.add(application)

    application.client_id = client_id
    application.client_secret_encrypted = encrypt_secret(client_secret)
    application.platform = platform or None
    application.write_user_id = actor_user_id
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
