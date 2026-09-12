"""Identifiants OAuth2 que la plateforme certifiée (SuperPDP) fournit au routeur, par
entreprise gérée (spec.md § 4.10, lot 6) — portés directement par `Company`
(`certified_platform_*`), distincts des applications OAuth que le routeur émet
lui-même pour ses consommateurs (§ 4.9.2, portées par `TargetApplication.parameters`,
lot 4)."""

from pyfrctc import pyfrctc as core
from pyfrctc.pyfrctc import PLATFORMS
from sqlalchemy.orm import Session

from app.config import settings
from app.models.referential import Company
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
    resolved_platform = platform or settings.certified_platform
    if resolved_platform not in PLATFORMS:
        return False, f"Plateforme AFNOR inconnue : {resolved_platform!r}"

    if settings.certified_platform_client_mode == "fake":
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


def get_credentials_application(db: Session, *, company_id: int) -> Company | None:
    """Retourne l'entreprise si des identifiants SuperPDP y sont configurés, sinon
    `None` (y compris si l'entreprise elle-même n'existe pas) — préserve le même
    contrat "configuré ou pas" qu'avant l'abandon de la table `oauth_applications`,
    pour ne pas impacter les appelants (`app/afnor/client/adapter.py`,
    `app/api/ihm/companies.py`)."""
    company = db.get(Company, company_id)
    if company is None or company.certified_platform_client_id is None:
        return None
    return company


def set_credentials(
    db: Session,
    *,
    company_id: int,
    client_id: str,
    client_secret: str,
    platform: str | None = None,
    actor_user_id: int | None = None,
) -> Company:
    """Enregistre (ou remplace) les identifiants fournis par SuperPDP pour cette
    entreprise. Le secret n'est jamais journalisé ni renvoyé en clair ensuite.
    `platform` : `None`/vide = plateforme par défaut du serveur (`settings.
    certified_platform`), sinon une clé de `pyfrctc.pyfrctc.PLATFORMS` (§ 4.10).
    `actor_user_id` : utilisateur à l'origine de l'appel (§ NF9), pour
    `write_user_id` (`AuditColumnsMixin`)."""
    if platform and platform not in PLATFORMS:
        raise ValueError(f"Plateforme AFNOR inconnue : {platform!r}")

    company = db.get(Company, company_id)
    if company is None:
        raise ValueError(f"Entreprise {company_id} introuvable.")

    company.certified_platform_client_id = client_id
    company.certified_platform_client_secret_encrypted = encrypt_secret(client_secret)
    company.certified_platform = platform or None
    company.write_user_id = actor_user_id
    # Un changement d'identifiants invalide le jeton précédemment mis en cache.
    company.certified_platform_token_cache = None
    db.commit()
    db.refresh(company)
    return company


def get_decrypted_secret(company: Company) -> str:
    if not company.certified_platform_client_secret_encrypted:
        raise ValueError(f"Aucun secret SuperPDP enregistré pour l'entreprise {company.id}.")
    return decrypt_secret(company.certified_platform_client_secret_encrypted)
