"""RouterSettingsService — configuration générale du routeur, instance unique
(spec.md § 6.1)."""

from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.models.settings import RouterSettings
from app.services import audit_trace_service
from app.services.mail_sender import Ipv4SmtpConnection, OutgoingMail, SmtpMailSender

SETTINGS_ID = 1


def get_settings(db: Session) -> RouterSettings:
    settings_row = db.get(RouterSettings, SETTINGS_ID)
    if settings_row is None:
        settings_row = RouterSettings(id=SETTINGS_ID)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return settings_row


def update_settings(db: Session, **fields) -> RouterSettings:
    settings_row = get_settings(db)
    for key, value in fields.items():
        if value is not None:
            setattr(settings_row, key, value)
    db.commit()
    db.refresh(settings_row)
    return settings_row


def _resolve_effective_smtp(db: Session, overrides: dict) -> SimpleNamespace:
    """Fusionne `overrides` (§ écran Configuration, boutons "Tester la connexion"/
    "Envoyer un courriel de test") avec les valeurs déjà enregistrées — un champ à
    `None` dans `overrides` retombe sur la valeur sauvegardée, jamais sur une valeur
    vide, pour que tester la connexion fonctionne même quand seul un champ du
    formulaire a été modifié sans être encore enregistré (notamment le mot de passe,
    jamais renvoyé par `GET /settings`)."""
    saved = get_settings(db)
    return SimpleNamespace(
        smtp_host=overrides.get("smtp_host") if overrides.get("smtp_host") is not None else saved.smtp_host,
        smtp_port=overrides.get("smtp_port") if overrides.get("smtp_port") is not None else saved.smtp_port,
        smtp_username=(
            overrides.get("smtp_username") if overrides.get("smtp_username") is not None else saved.smtp_username
        ),
        smtp_password=(
            overrides.get("smtp_password") if overrides.get("smtp_password") is not None else saved.smtp_password
        ),
        smtp_use_tls=(
            overrides.get("smtp_use_tls") if overrides.get("smtp_use_tls") is not None else saved.smtp_use_tls
        ),
        smtp_from_address=(
            overrides.get("smtp_from_address")
            if overrides.get("smtp_from_address") is not None
            else saved.smtp_from_address
        ),
    )


def test_smtp_connection(db: Session, overrides: dict) -> tuple[bool, str | None]:
    """Aller-retour réseau réel (connexion + STARTTLS + authentification si des
    identifiants sont fournis) — sans envoyer aucun message, à l'image de
    `certified_platform_credentials_service.test_connection` (§ 4.10) pour les
    identifiants SuperPDP. Renvoie `(ok, message_erreur)`.

    Le résultat (succès ou échec, avec le message d'erreur SMTP brut) est tracé dans
    `TechnicalLog` (§ 6.1, `origin="ihm_settings_smtp"`) — seule table qui porte à la
    fois un statut et un détail texte, contrairement à `AuditLog` (NF9, qui ne trace
    que l'action et sa cible, pas son issue) ou `FlowTrace` (NF1, réservé aux échanges
    AFNOR/SuperPDP)."""
    smtp_config = _resolve_effective_smtp(db, overrides)
    if not smtp_config.smtp_host:
        error = "Aucun hôte SMTP configuré."
        _record_smtp_technical_log(db, log_type="smtp_test_connection", status="error", details=error)
        return False, error
    try:
        with Ipv4SmtpConnection(smtp_config.smtp_host, smtp_config.smtp_port, timeout=10) as smtp:
            if smtp_config.smtp_use_tls:
                smtp.starttls()
            if smtp_config.smtp_username:
                smtp.login(smtp_config.smtp_username, smtp_config.smtp_password or "")
    except Exception as exc:  # noqa: BLE001 — connectivité/identifiants tiers, cause imprévisible
        _record_smtp_technical_log(db, log_type="smtp_test_connection", status="error", details=str(exc))
        return False, str(exc)
    _record_smtp_technical_log(db, log_type="smtp_test_connection", status="success")
    return True, None


def send_test_email(db: Session, overrides: dict, *, to_address: str) -> tuple[bool, str | None]:
    """Envoi réel d'un message de test — réutilise `SmtpMailSender`, le même chemin
    de code que les envois applicatifs (§ 4.5/§ 4.9.1), pour que ce bouton vérifie
    effectivement ce qui sera utilisé en production plutôt qu'un chemin parallèle.

    Résultat tracé dans `TechnicalLog`, même rationale que `test_smtp_connection`
    ci-dessus."""
    smtp_config = _resolve_effective_smtp(db, overrides)
    if not smtp_config.smtp_host:
        error = "Aucun hôte SMTP configuré."
        _record_smtp_technical_log(db, log_type="smtp_send_test_email", status="error", details=error)
        return False, error
    if not smtp_config.smtp_from_address:
        # Sans ce garde-fou, `EmailMessage["From"] = None` sérialise littéralement la
        # chaîne "None" comme adresse d'expédition — un serveur SMTP distant (ex.
        # Exchange Online) la rejette alors avec un 5.1.7 "Invalid address" qui ne dit
        # rien de la vraie cause (aucune adresse expéditeur configurée), en plus
        # d'exposer le mot "None" dans les logs du fournisseur de messagerie.
        error = "Aucune adresse expéditeur SMTP configurée."
        _record_smtp_technical_log(db, log_type="smtp_send_test_email", status="error", details=error)
        return False, error
    mail = OutgoingMail(
        to=[to_address],
        cc=[],
        bcc=[],
        subject="Routeur de factures électroniques — courriel de test",
        body="Ceci est un courriel de test envoyé depuis la page Configuration du routeur.",
    )
    try:
        SmtpMailSender().send(mail, router_settings=smtp_config)
    except Exception as exc:  # noqa: BLE001 — connectivité/identifiants tiers, cause imprévisible
        _record_smtp_technical_log(
            db, log_type="smtp_send_test_email", status="error", details=f"{to_address} : {exc}"
        )
        return False, str(exc)
    _record_smtp_technical_log(db, log_type="smtp_send_test_email", status="success", details=to_address)
    return True, None


def _record_smtp_technical_log(
    db: Session, *, log_type: str, status: str, details: str | None = None
) -> None:
    audit_trace_service.record_technical_log(
        db, log_type=log_type, origin="ihm_settings_smtp", status=status, details=details
    )
