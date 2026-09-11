from datetime import datetime

from pydantic import BaseModel, Field


class FailedInvoiceRoutingRead(BaseModel):
    id: int
    invoice_id: int
    invoice_number: str
    emitter_siren: str
    target_application_id: int
    target_application_name: str
    transfer_status: str
    attempt_count: int
    next_attempt_at: datetime | None


class ReplayRoutingsRequest(BaseModel):
    """Rejeu manuel en masse (§ 4.7) : à la maille d'une ou plusieurs `InvoiceRouting`
    (une cible unique, ou toutes les cibles en échec d'une facture — l'IHM se contente
    de pré-cocher toutes les cases d'une même facture pour ce second cas)."""

    routing_ids: list[int] = Field(min_length=1)


class ReplayRoutingResult(BaseModel):
    routing_id: int
    success: bool
