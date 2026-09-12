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
    """Paramètres OAuth éditables d'une application `afnor_api` (§ 4.9.2) — le
    `client_id`/secret ne sont jamais renvoyés ici (générés une seule fois à la
    création, cf. `TargetApplicationCreated`)."""

    model_config = ConfigDict(from_attributes=True)

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


class RoutingRuleRead(AuditColumnsRead):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_directory_id: int
    target_application_id: int
