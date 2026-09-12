from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CurrentUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
    company_ids: list[int]
    previous_login_at: datetime | None = Field(
        description=(
            "Avant-dernière connexion (pas la connexion en cours) — cf. "
            "audit_trace_service.get_previous_login, pour repérer une connexion "
            "inhabituelle depuis la sidebar."
        )
    )


class CurrentUserStatus(BaseModel):
    oidc_mode: str
    authenticated: bool
    user: CurrentUserRead | None = None
