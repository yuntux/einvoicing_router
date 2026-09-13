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
    """`has_file` : idem, dérivé de `file_path is not None` sans jamais exposer le
    contenu (téléchargé via un endpoint dédié, cf. `invoices.py`)."""

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


class RetryAfnorFlow(BaseModel):
    """Corps optionnel du renvoi d'un `AfnorFlow` sortant en erreur (§ IHM fiche
    facture) : absent (`null`/corps vide), le CDAR est renvoyé tel quel ; fourni, ces
    valeurs remplacent motif/action/commentaire de l'événement avant renvoi."""

    reason: str | None = None
    action: str | None = None
    comment: str | None = None


class StatusCatalogEntry(BaseModel):
    key: str
    label: str
    cdar_code: str
    mdt88_code: str | None
    manual_side: str | None
    requires_detail: bool
    requires_confirmation: bool
    # Sous-ensemble de `reasons` accepté pour CE statut par SuperPDP (§ lifecycle_catalog
    # StatusInfo.allowed_reasons) — vide tant que `requires_detail` est faux.
    allowed_reasons: list[str] = Field(default_factory=list)


class LifecycleCatalogRead(BaseModel):
    statuses: list[StatusCatalogEntry]
    reasons: dict[str, str]
    actions: dict[str, str] = Field(default_factory=dict)
