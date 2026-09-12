"""Client AFNOR "fake" — fixtures en mémoire, pour développer/tester sans
identifiants SuperPDP réels (spec.md § 10.1, décision de conception du lot 2)."""

from datetime import datetime

from app.afnor.client.base import RawIncomingCdar, RawInvoice


class FakeCertifiedPlatformClient:
    def __init__(
        self,
        invoices: list[RawInvoice] | None = None,
        incoming_cdars: list[RawIncomingCdar] | None = None,
    ) -> None:
        self._invoices = invoices or []
        self._incoming_cdars = incoming_cdars or []

    def fetch_received_invoices(
        self, *, company_siren: str, since: datetime | None = None
    ) -> list[RawInvoice]:
        # Client de test : ignore company_siren/since, renvoie simplement les factures
        # fournies au constructeur (un vrai client filtrerait côté SuperPDP).
        return list(self._invoices)

    def fetch_incoming_lifecycle_events(
        self, *, company_siren: str, since: datetime | None = None
    ) -> list[RawIncomingCdar]:
        return list(self._incoming_cdars)
