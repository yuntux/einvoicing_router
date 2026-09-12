from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.referential import OAuthAppType, RoutingMethod
from app.schemas.mixins import AuditColumnsRead
from app.schemas.validators import validate_siren, validate_siret


class PartnerDirectoryCreate(BaseModel):
    siren: str = Field(min_length=9, max_length=9)
    siret: str | None = Field(default=None, min_length=14, max_length=14)
    name: str = Field(min_length=1, max_length=255)

    _validate_siren = field_validator("siren")(validate_siren)

    @field_validator("siret")
    @classmethod
    def _validate_siret(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_siret(value)


class PartnerDirectoryRead(AuditColumnsRead):
    model_config = ConfigDict(from_attributes=True)

    id: int
    siren: str
    siret: str | None
    name: str


class TargetApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    routing_method: RoutingMethod
    company_id: int
    parameters: dict = Field(default_factory=dict)


class TargetApplicationOAuthRead(BaseModel):
    """Paramètres OAuth d'une application `afnor_api` (§ 4.9.2) — `client_id` reste
    affiché en permanence (identifiant public, comme sur la fiche application de
    SuperPDP), contrairement au secret, jamais renvoyé après sa création (une seule
    fois, en clair, cf. `TargetApplicationCreated`)."""

    model_config = ConfigDict(from_attributes=True)

    client_id: str
    app_type: OAuthAppType
    redirect_urls: str | None
    preferred_conversion_format: str | None
    webhook_url: str | None


class TargetApplicationRead(AuditColumnsRead):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    routing_method: RoutingMethod
    company_id: int
    oauth_application_id: int | None
    oauth_application: TargetApplicationOAuthRead | None
    parameters: dict
    is_active: bool


class TargetApplicationStatusUpdate(BaseModel):
    is_active: bool


class TargetApplicationLookup(BaseModel):
    """Référence minimale (id + nom + entreprise) — pas de paramètres (destinataires
    mail, webhook OAuth...) ni de colonnes d'audit. Exposée à tout utilisateur
    authentifié (contrairement à `TargetApplicationRead`, admin-only) car des pages
    non admin-only (ex. Règles de routage) ont besoin d'afficher le nom d'une
    application cible et de son entreprise, sans donner accès à la page Applications
    cibles elle-même (§ NF4)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    company_id: int


class TargetApplicationUpdate(BaseModel):
    """Modification des paramètres propres à la méthode de routage (§ 4.9.1/4.9.2) —
    `routing_method` et `company_id` restent figés après création (casserait le
    rattachement OAuth existant ou les règles de routage déjà créées pour ce canal)."""

    name: str = Field(min_length=1, max_length=255)
    parameters: dict = Field(default_factory=dict)


class TargetApplicationCreated(TargetApplicationRead):
    """Réponse de création : porte le secret OAuth en clair une seule fois
    (méthode afnor_api uniquement, § 4.9.2) — jamais renvoyé ensuite."""

    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None


class RoutingRuleSetActive(BaseModel):
    """Coche/décoche la case (fournisseur, application cible) de la matrice IHM
    (§ 4.3) — `active=True` crée la règle si absente, `active=False` la supprime."""

    active: bool
    reroute_existing: bool = Field(
        default=True,
        description=(
            "Sans objet si active=False. Si True (défaut), les factures déjà reçues de "
            "ce fournisseur et pas encore routées vers cette cible sont routées "
            "immédiatement. Si False, seules les prochaines factures reçues seront "
            "concernées."
        ),
    )


class RoutingRuleRead(AuditColumnsRead):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_directory_id: int
    target_application_id: int
