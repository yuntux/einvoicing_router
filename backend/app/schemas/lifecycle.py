from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class LifecycleEventDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reason: str | None
    action: str | None
    comment: str | None


class LifecycleEventPaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: float
    currency: str
    payment_date: date


class LifecycleEventAttachmentRead(BaseModel):
    """`has_file` : construit explicitement côté endpoint (jamais par `from_attributes`
    automatique) — dérivé de `file_path`, jamais le contenu du fichier lui-même."""

    id: int
    filename: str
    has_file: bool


class AfnorFlowRead(BaseModel):
    """`has_file` : idem, dérivé de `file_bin is not None` sans jamais exposer les
    octets bruts (téléchargés via un endpoint dédié, cf. `invoices.py`)."""

    id: int
    flow_id: str | None
    direction: str
    flow_type: str
    syntax: str
    processing_rule: str | None
    state: str
    has_file: bool


class LifecycleEventRead(BaseModel):
    """Toujours construit explicitement (cf. `invoices.py`), jamais par
    `from_attributes` automatique : `attachments`/`payments` mêlent des sous-schémas
    qui, eux, dérivent un champ (`has_file`) absent du modèle ORM."""

    id: int
    invoice_id: int
    event_datetime: datetime
    status: str
    direction: str
    amount: float | None
    currency: str | None
    details: list[LifecycleEventDetailRead]
    payments: list[LifecycleEventPaymentRead]
    attachments: list[LifecycleEventAttachmentRead]
    # Flux CDAR technique associé (§ 6.2) — permet à l'IHM de fusionner en une seule
    # ligne le statut métier et son état de transmission, sans requête séparée sur
    # "Flux AFNOR" (cf. maquette popin facture).
    afnor_flow: AfnorFlowRead | None


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
