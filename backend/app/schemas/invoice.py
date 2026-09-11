from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


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
    # Obtenus par jointure sur AuditLog (§ 6.1) — jamais dénormalisés sur Invoice.
    last_download_at: datetime | None = None
    last_download_by: str | None = None


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
