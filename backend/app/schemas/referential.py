from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.referential import OAuthAppType, RoutingMethod
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


class PartnerDirectoryRead(BaseModel):
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


class TargetApplicationRead(BaseModel):
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


class RoutingRuleDatesMixin(BaseModel):
    start_date: date
    end_date: date | None = None

    @model_validator(mode="after")
    def _validate_dates(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date ne peut pas être antérieure à start_date")
        return self


class RoutingRuleCreate(RoutingRuleDatesMixin):
    partner_directory_id: int
    target_application_id: int
    active: bool = True


class RoutingRuleUpsert(RoutingRuleDatesMixin):
    """Crée ou met à jour la règle d'un couple (fournisseur, application cible) —
    matrice de la page Règles de routage : chaque paire, même sans règle existante,
    y est éditable directement."""


class RoutingRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_directory_id: int
    target_application_id: int
    start_date: date
    end_date: date | None
    active: bool
