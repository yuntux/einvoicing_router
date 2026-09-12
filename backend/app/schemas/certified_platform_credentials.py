from pydantic import BaseModel, Field


class CertifiedPlatformCredentialsCreate(BaseModel):
    client_id: str = Field(min_length=1, max_length=255)
    client_secret: str = Field(min_length=1)
    platform: str | None = Field(default=None, max_length=50)


class CertifiedPlatformCredentialsStatus(BaseModel):
    configured: bool
    client_id: str | None = None
    platform: str | None = None


class AfnorPlatform(BaseModel):
    key: str
    label: str
