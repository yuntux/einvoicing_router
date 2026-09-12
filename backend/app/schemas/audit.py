"""Lecture des trois journaux de traçabilité (spec.md § 6.1) — écriture déjà couverte
par `app.services.audit_trace_service`, ces schémas ne servent qu'à leur consultation
depuis l'IHM."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FlowTraceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    correlation_id: str
    direction: str
    afnor_api_version: str
    request: dict
    response: dict
    http_status: int
    created_at: datetime


class TechnicalLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    log_type: str
    origin: str
    company_id: int | None
    status: str
    new_count: int
    updated_count: int
    details: str | None
    created_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    user_email: str | None = None
    action: str
    target: str
    ip_address: str | None
    created_at: datetime
