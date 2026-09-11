from pydantic import BaseModel, ConfigDict


class CurrentUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
    company_ids: list[int]


class CurrentUserStatus(BaseModel):
    oidc_mode: str
    authenticated: bool
    user: CurrentUserRead | None = None
