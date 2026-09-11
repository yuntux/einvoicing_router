from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    siren: str = Field(min_length=9, max_length=9)
    name: str = Field(min_length=1, max_length=255)


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    siren: str
    name: str
