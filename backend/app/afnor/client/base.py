"""Interface commune des clients AFNOR XP Z12-013 côté SuperPDP (spec.md § 4.1/§ 4.8).

Deux implémentations : `FakeSuperPDPClient` (fixtures, utilisée tant qu'aucun accès
SuperPDP réel n'est branché) et, au lot 6, un client réel basé sur `pyfrctc`. Les deux
respectent `SuperPDPClientProtocol` afin que le reste du code (ingestion, tests) soit
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

    superpdp_flow_id: str
    emitter_siren: str
    invoice_number: str
    invoice_date: date
    file_name: str
    file_content: bytes
    emitter_siret: str | None = None
    due_date: date | None = None
    invoice_type: str = "invoice"
    amount_total: float | None = None
    amount_excl_tax: float | None = None
    currency: str = "EUR"
    syntax: str = "Factur-X"
    processing_rule: str = "B2B"
    afnor_api_version: str = "v1"
    superpdp_submitted_at: datetime | None = None
    superpdp_updated_at: datetime | None = None
    raw_metadata: dict = field(default_factory=dict)


class SuperPDPClientProtocol(Protocol):
    def fetch_received_invoices(
        self, *, company_siren: str, since: datetime | None = None
    ) -> list[RawInvoice]:
        """Retourne les factures reçues pour l'entreprise gérée (§ 4.1)."""
        ...
