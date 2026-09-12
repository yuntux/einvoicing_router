from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.validators import validate_siren


class CompanyCreate(BaseModel):
    siren: str = Field(min_length=9, max_length=9)
    name: str = Field(min_length=1, max_length=255)

    _validate_siren = field_validator("siren")(validate_siren)


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    siren: str
    name: str
