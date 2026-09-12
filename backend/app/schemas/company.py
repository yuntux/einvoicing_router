from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.mixins import AuditColumnsRead
from app.schemas.validators import validate_siren


class CompanyCreate(BaseModel):
    siren: str = Field(min_length=9, max_length=9)
    name: str = Field(min_length=1, max_length=255)

    _validate_siren = field_validator("siren")(validate_siren)


class CompanyRead(AuditColumnsRead):
    model_config = ConfigDict(from_attributes=True)

    id: int
    siren: str
    name: str


class CompanyLookup(BaseModel):
    """Référence minimale (id + nom) — pas de SIREN ni de colonnes d'audit. Exposée à
    tout utilisateur authentifié (pas seulement les admins, contrairement à
    `CompanyRead`) car des pages non admin-only (ex. Règles de routage) ont besoin
    d'afficher un nom d'entreprise sans donner accès à la page Entreprises elle-même
    (§ NF4)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
