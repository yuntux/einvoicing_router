from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LifecycleEventDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reason: str | None
    action: str | None
    comment: str | None


class LifecycleEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    event_datetime: datetime
    status: str
    direction: str
    details: list[LifecycleEventDetailRead]


class CreateManualLifecycleEvent(BaseModel):
    status: str
    reason: str | None = None
    action: str | None = None
    comment: str | None = None
    confirmed: bool = False


class StatusCatalogEntry(BaseModel):
    key: str
    label: str
    cdar_code: str
    mdt88_code: str | None
    manual_side: str | None
    requires_detail: bool
    requires_confirmation: bool


class LifecycleCatalogRead(BaseModel):
    statuses: list[StatusCatalogEntry]
    reasons: dict[str, str]
    actions: dict[str, str] = Field(default_factory=dict)
