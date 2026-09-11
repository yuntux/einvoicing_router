from pydantic import BaseModel, ConfigDict, Field


class RouterSettingsRead(BaseModel):
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


class BillingManagerContactCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class BillingManagerContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
