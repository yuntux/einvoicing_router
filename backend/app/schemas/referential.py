from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.referential import RoutingMethod


class PartnerDirectoryCreate(BaseModel):
    siren: str = Field(min_length=9, max_length=9)
    siret: str | None = Field(default=None, min_length=14, max_length=14)
    name: str = Field(min_length=1, max_length=255)


class PartnerDirectoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    siren: str
    siret: str | None
    name: str


class TargetApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    routing_method: RoutingMethod
    company_id: int | None = None
    parameters: dict = Field(default_factory=dict)


class TargetApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    routing_method: RoutingMethod
    company_id: int | None
    parameters: dict


class RoutingRuleCreate(BaseModel):
    partner_directory_id: int
    target_application_id: int
    start_date: date | None = None
    end_date: date | None = None
    active: bool = True


class RoutingRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_directory_id: int
    target_application_id: int
    start_date: date | None
    end_date: date | None
    active: bool
