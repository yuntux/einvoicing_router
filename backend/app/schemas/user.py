from pydantic import BaseModel, Field


class UserRead(BaseModel):
    id: int
    email: str
    name: str
    role: str
    company_ids: list[int]


class UserAccessUpdate(BaseModel):
    role: str = Field(pattern="^(admin|user)$")
    company_ids: list[int] = Field(default_factory=list)
