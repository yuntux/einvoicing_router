"""Interface commune des clients AFNOR XP Z12-013 côté SuperPDP (spec.md § 4.1/§ 4.8).

Deux implémentations : `FakeCertifiedPlatformClient` (fixtures, utilisée tant qu'aucun accès
SuperPDP réel n'est branché) et, au lot 6, un client réel basé sur `pyfrctc`. Les deux
respectent `CertifiedPlatformClientProtocol` afin que le reste du code (ingestion, tests) soit
indépendant de l'implémentation effective (cf. décision d'architecture § 4.8).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol


@dataclass
class RawInvoice:
    """Facture reçue telle que renvoyée par l'API AFNOR de SuperPDP (représentation
    minimale, indépendante de la version de l'API — le mapping vers la version
    effective se fera dans `afnor/versioning/`, § 4.8)."""

    certified_platform_flow_id: str
    emitter_siren: str
    invoice_number: str
    invoice_date: date
    file_name: str
    file_content: bytes
    emitter_siret: str | None = None
    # Raison sociale de l'émetteur, si le flux AFNOR la porte (§ 4.4) — sert de nom
    # à l'entrée `PartnerDirectory` auto-créée à la première facture d'un fournisseur
    # inconnu, à la place du placeholder générique quand elle est disponible.
    emitter_name: str | None = None
    due_date: date | None = None
    invoice_type: str = "invoice"
    amount_total: float | None = None
    amount_excl_tax: float | None = None
    # Déclaré dans le fichier (ram:TaxTotalAmount / cac:TaxTotal⁄cbc:TaxAmount) —
    # jamais recalculé par soustraction, cf. `app.afnor.invoice_parsing.ParsedInvoiceFields`.
    amount_tax: float | None = None
    currency: str = "EUR"
    syntax: str = "Factur-X"
    processing_rule: str = "B2B"
    afnor_api_version: str = "v1"
    certified_platform_submitted_at: datetime | None = None
    certified_platform_updated_at: datetime | None = None
    raw_metadata: dict = field(default_factory=dict)
    # Champs de l'enveloppe de transport du flux AFNOR (schéma officiel "AFNOR Flow
    # Service", cf. app/afnor/invoice_parsing.py) — distincts des champs métier de la
    # facture ci-dessus (émetteur, montants...), qui eux ne figurent jamais dans le
    # Metadata du flux et doivent être extraits du fichier facture lui-même.
    flow_profile: str | None = None
    processing_rule_source: str | None = None
    tracking_id: str | None = None
    flow_direction: str | None = None
    flow_type: str | None = None
    flow_name: str | None = None
    ack_status: str | None = None
    ack_details: str | None = None


@dataclass
class RawIncomingCdar:
    """Message de cycle de vie CDAR reçu (§ 4.2, flux `SupplierInvoiceLC`) — contenu
    brut non interprété : le rattachement à la facture concernée et l'interprétation
    du statut se font en aval (`app.services.lifecycle_ingestion_service`), pas ici,
    pour garder ce client "bête" (cf. docstring de module)."""

    flow_id: str
    xml_bytes: bytes
    flow_type: str | None = None


class CertifiedPlatformClientProtocol(Protocol):
    def fetch_received_invoices(
        self, *, company_siren: str, since: datetime | None = None
    ) -> list[RawInvoice]:
        """Retourne les factures reçues pour l'entreprise gérée (§ 4.1)."""
        ...

    def fetch_incoming_lifecycle_events(
        self, *, company_siren: str, since: datetime | None = None
    ) -> list[RawIncomingCdar]:
        """Retourne les CDAR entrants (messages de cycle de vie, § 4.2) pour
        l'entreprise gérée — distinct de `fetch_received_invoices` : jamais de
        nouvelle facture créée à partir de ces flux (cf. l'incident du flux
        ie_78332)."""
        ...
