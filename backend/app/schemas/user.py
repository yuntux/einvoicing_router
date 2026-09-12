from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.mixins import AuditColumnsRead


class UserRead(AuditColumnsRead):
    id: int
    email: str
    name: str | None
    role: str
    company_ids: list[int]
    is_active: bool
    has_logged_in: bool
    last_login_at: datetime | None


class UserCreate(BaseModel):
    """Pré-provisionnement d'un compte (§ NF4) : seul l'email est requis — le nom est
    complété automatiquement depuis les claims OIDC lors de la première connexion de
    son titulaire (cf. `user_service.resolve_login_user`)."""

    email: str = Field(min_length=3, max_length=255)
    name: str | None = None


class UserAccessUpdate(BaseModel):
    role: str = Field(pattern="^(admin|user|readonly)$")
    company_ids: list[int] = Field(default_factory=list)
    is_active: bool = True
