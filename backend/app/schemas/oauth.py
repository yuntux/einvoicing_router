from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class DirectoryLookupRead(BaseModel):
    partner_id: int
    siren: str
    name: str
    created: bool
