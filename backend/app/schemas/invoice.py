from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.lifecycle import AfnorFlowRead
from app.schemas.validators import validate_siren, validate_siret


class InvoiceRoutingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_application_id: int
    transfer_status: str
    attempt_count: int
    next_attempt_at: datetime | None


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
    certified_platform_flow_id: str
    certified_platform_submitted_at: datetime | None
    certified_platform_updated_at: datetime | None
    amount_total: float | None
    amount_excl_tax: float | None
    # Déclaré dans le fichier (pas recalculé par soustraction, cf.
    # app.afnor.invoice_parsing).
    amount_tax: float | None
    currency: str | None
    syntax: str | None
    processing_rule: str | None
    afnor_api_version: str | None
    received_at: datetime
    # Enveloppe de transport du flux AFNOR d'origine (schéma officiel "AFNOR Flow
    # Service") — distincte des champs métier ci-dessus, extraits du fichier facture.
    flow_profile: str | None
    processing_rule_source: str | None
    tracking_id: str | None
    flow_direction: str | None
    flow_type: str | None
    flow_name: str | None
    ack_status: str | None
    ack_details: str | None
    # Obtenus par jointure sur AuditLog (§ 6.1) — jamais dénormalisés sur Invoice.
    last_download_at: datetime | None = None
    last_download_by: str | None = None
    # Statut de routage par application cible (§ 4.7/§ 8.3) — utilisé par la liste
    # des factures pour afficher un badge par application de l'entreprise, sans
    # nécessiter un aller-retour par facture vers le détail.
    routings: list[InvoiceRoutingRead] = Field(default_factory=list)
    # Raison sociale de l'émetteur (PartnerDirectory) et de l'entreprise réceptrice
    # (Company) — obtenues par jointure, jamais dénormalisées sur Invoice (§ 6.1).
    # Renseignées explicitement par les endpoints ci-dessous, pas par
    # `from_attributes` automatique.
    emitter_name: str | None = None
    company_name: str | None = None
    company_siren: str | None = None


class InvoiceDetailRead(InvoiceRead):
    # Renseigné explicitement par l'endpoint (§ 6.2) — `has_file` dérivé, pas de
    # conversion `from_attributes` automatique possible pour ce sous-schéma.
    afnor_flows: list[AfnorFlowRead] = Field(default_factory=list)


class SimulateInvoiceReception(BaseModel):
    """Simule la réception d'une facture via SuperPDP (dev/tests — remplace le cron réel
    jusqu'au lot 5/6)."""

    company_id: int
    emitter_siren: str = Field(min_length=9, max_length=9)
    emitter_siret: str | None = None
    emitter_name: str | None = None
    invoice_number: str
    invoice_date: date
    due_date: date | None = None
    invoice_type: str = "invoice"
    amount_total: float | None = None
    amount_excl_tax: float | None = None
    amount_tax: float | None = None
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
