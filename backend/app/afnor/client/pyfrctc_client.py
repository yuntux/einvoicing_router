"""Client AFNOR XP Z12-013 réel, basé sur **pyfrctc** (spec.md § 4.1/§ 4.8/NF7, lot 6).

Implémente `SuperPDPClientProtocol` à partir d'une session pyfrctc déjà authentifiée
(construite par `AfnorClientAdapter`, qui gère les identifiants/le cache de jeton par
entreprise) — cette classe reste volontairement "bête" : aucun accès DB, uniquement de
la traduction entre l'API pyfrctc et `RawInvoice`, pour rester testable avec une session
mockée (symétrique à `FakeSuperPDPClient`).

Note de conception : le mapping exact des champs de métadonnées renvoyés par SuperPDP
(numéro de facture, montants, syntaxe...) n'est pas figé par une documentation
publique complète à ce stade — les clés extraites ci-dessous couvrent les champs déjà
stabilisés par `pyfrctc._parse_flow_dict` (id, dates, direction, état) et une liste de
noms de clés plausibles pour le reste, à affiner lors des premiers essais contre le
bac à sable réel (§ 10.4, `integration_tests_sandbox/`)."""

from datetime import date, datetime

from pyfrctc import pyfrctc as core

from app.afnor.client.base import RawInvoice

RECEIVED_INVOICE_FLOW_TYPES = ["SupplierInvoice", "SupplierInvoiceLC"]


def _first(metadata: dict, *keys: str, default=None):
    for key in keys:
        if metadata.get(key) is not None:
            return metadata[key]
    return default


def _to_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    return datetime.utcnow().date()


class PyfrctcSuperPDPClient:
    """Un client par session pyfrctc authentifiée (une session = une entreprise)."""

    def __init__(self, session) -> None:
        self._session = session

    def fetch_received_invoices(
        self, *, company_siren: str, since: datetime | None = None
    ) -> list[RawInvoice]:
        updated_after = since or datetime(2000, 1, 1)
        flows = core.search_flows_parsed(
            self._session,
            updated_after=updated_after,
            flow_direction="in",
            flow_type=RECEIVED_INVOICE_FLOW_TYPES,
        )

        invoices: list[RawInvoice] = []
        for flow in flows:
            flow_id = flow.get("id") or flow.get("flowId")
            if not flow_id:
                continue
            metadata = core.get_flow_metadata_parsed(self._session, flow_id)
            file_content = core.get_flow(self._session, flow_id, doc_type="Original")
            file_name = _first(metadata, "fileName", "filename", default=f"{flow_id}.xml")

            invoices.append(
                RawInvoice(
                    superpdp_flow_id=flow_id,
                    emitter_siren=_first(metadata, "emitterSiren", "senderSiren", default=""),
                    emitter_siret=_first(metadata, "emitterSiret", "senderSiret"),
                    invoice_number=_first(
                        metadata, "invoiceNumber", "documentNumber", default=flow_id
                    ),
                    invoice_date=_to_date(
                        _first(metadata, "invoiceDate", "issueDate", default=flow.get("submitted_at"))
                    ),
                    due_date=None,
                    invoice_type=_first(metadata, "invoiceType", default="invoice"),
                    amount_total=_first(metadata, "amountTotal", "totalAmount"),
                    amount_excl_tax=_first(metadata, "amountExclTax", "totalAmountExclTax"),
                    currency=_first(metadata, "currency", default="EUR"),
                    syntax=_first(metadata, "syntax", default="Factur-X"),
                    processing_rule=_first(metadata, "processingRule", default="B2B"),
                    afnor_api_version=core.AFNOR_API_VERSION,
                    superpdp_submitted_at=flow.get("submitted_at"),
                    superpdp_updated_at=flow.get("updated_at"),
                    file_name=file_name,
                    file_content=file_content,
                    raw_metadata=metadata,
                )
            )
        return invoices
