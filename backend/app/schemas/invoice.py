from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.lifecycle import AfnorFlowRead
from app.schemas.validators import validate_siren, validate_siret


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    partner_directory_id: int | None
    emitter_siren: str
    emitter_siret: str | None
    invoice_number: str
    invoice_date: date
    due_date: date | None
    invoice_type: str
    lifecycle_status: str | None
    file_path: str
    superpdp_flow_id: str
    superpdp_submitted_at: datetime | None
    superpdp_updated_at: datetime | None
    amount_total: float | None
    amount_excl_tax: float | None
    currency: str | None
    syntax: str | None
    processing_rule: str | None
    afnor_api_version: str | None
    received_at: datetime
    # Obtenus par jointure sur AuditLog (§ 6.1) — jamais dénormalisés sur Invoice.
    last_download_at: datetime | None = None
    last_download_by: str | None = None


class InvoiceRoutingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_application_id: int
    transfer_status: str
    attempt_count: int
    next_attempt_at: datetime | None


class InvoiceDetailRead(InvoiceRead):
    routings: list[InvoiceRoutingRead]
    emitter_name: str | None = None
    # Renseigné explicitement par l'endpoint (§ 6.2) — `has_file` dérivé, pas de
    # conversion `from_attributes` automatique possible pour ce sous-schéma.
    afnor_flows: list[AfnorFlowRead] = Field(default_factory=list)


class SimulateInvoiceReception(BaseModel):
    """Simule la réception d'une facture via SuperPDP (dev/tests — remplace le cron réel
    jusqu'au lot 5/6)."""

    company_id: int
    emitter_siren: str = Field(min_length=9, max_length=9)
    emitter_siret: str | None = None
    invoice_number: str
    invoice_date: date
    due_date: date | None = None
    invoice_type: str = "invoice"
    amount_total: float | None = None
    amount_excl_tax: float | None = None
    currency: str = "EUR"
    syntax: str = "Factur-X"
    processing_rule: str = "B2B"

    _validate_emitter_siren = field_validator("emitter_siren")(validate_siren)

    @field_validator("emitter_siret")
    @classmethod
    def _validate_emitter_siret(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_siret(value)
