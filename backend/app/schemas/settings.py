from pydantic import BaseModel, ConfigDict, Field

from app.schemas.mixins import AuditColumnsRead


class RouterSettingsRead(AuditColumnsRead):
    model_config = ConfigDict(from_attributes=True)

    technical_log_retention_days: int
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_use_tls: bool
    smtp_from_address: str | None
    ihm_ip_allowlist: str | None
    afnor_api_ip_allowlist: str | None


class RouterSettingsUpdate(BaseModel):
    technical_log_retention_days: int | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool | None = None
    smtp_from_address: str | None = None
    ihm_ip_allowlist: str | None = None
    afnor_api_ip_allowlist: str | None = None


class SmtpOverrides(BaseModel):
    """Valeurs SMTP à utiliser pour un test (connexion ou envoi), au lieu des valeurs
    enregistrées — tous les champs sont optionnels : un champ omis/`null` retombe sur
    la valeur déjà sauvegardée dans `RouterSettings` (même sémantique que
    `RouterSettingsUpdate`), pour que tester une connexion fonctionne même quand
    seul un champ (ex. le mot de passe, jamais renvoyé par `GET`, § RouterSettingsRead)
    a été modifié dans le formulaire sans avoir encore été enregistré."""

    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool | None = None
    # Ignoré par le test de connexion (aucun message envoyé, donc pas d'expéditeur à
    # valider) mais accepté ici pour que le frontend envoie une forme unique de
    # surcharge pour les deux boutons — utilisé par `send_test_email`.
    smtp_from_address: str | None = None


class SmtpTestResult(BaseModel):
    ok: bool
    error: str | None = None


class SmtpSendTestEmailRequest(SmtpOverrides):
    to_address: str = Field(min_length=3, max_length=255)


class BillingManagerContactCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class BillingManagerContactRead(AuditColumnsRead):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
