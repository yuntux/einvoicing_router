"""Client AFNOR XP Z12-013 réel, basé sur **pyfrctc** (spec.md § 4.1/§ 4.8/NF7, lot 6).

Implémente `SuperPDPClientProtocol` à partir d'une session pyfrctc déjà authentifiée
(construite par `AfnorClientAdapter`, qui gère les identifiants/le cache de jeton par
entreprise) — cette classe reste volontairement "bête" : aucun accès DB, uniquement de
la traduction entre l'API pyfrctc et `RawInvoice`, pour rester testable avec une session
mockée (symétrique à `FakeSuperPDPClient`).

Les clés lues sur `metadata` (renvoyé par `get_flow_metadata_parsed`) sont celles du
schéma officiel "AFNOR Flow Service" (`GET /flows/{id}?docType=Metadata` → objet
`Flow`) : flowId, submittedAt, updatedAt, flowProfile, flowSyntax, processingRule,
processingRuleSource, name, trackingId, flowDirection, flowType, acknowledgement —
uniquement l'enveloppe de transport du flux. Aucun champ métier de la facture
(émetteur, montants, numéro...) n'y figure : ces champs sont extraits du fichier
facture lui-même via `app.afnor.invoice_parsing` (cf. ce module pour le détail)."""

from datetime import date, datetime

from pyfrctc import pyfrctc as core

from app.afnor.client.base import RawInvoice
from app.afnor.invoice_parsing import invoice_type_from_code, parse_invoice_fields

RECEIVED_INVOICE_FLOW_TYPES = ["SupplierInvoice", "SupplierInvoiceLC"]


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
            flow_id = flow.get("flowId") or flow.get("id")
            if not flow_id:
                continue
            metadata = core.get_flow_metadata_parsed(self._session, flow_id)
            file_content = core.get_flow(self._session, flow_id, doc_type="Original")

            flow_syntax = metadata.get("flowSyntax")
            parsed = parse_invoice_fields(file_content, flow_syntax)
            ack_details = metadata.get("ap_error_details")

            invoices.append(
                RawInvoice(
                    superpdp_flow_id=flow_id,
                    emitter_siren=parsed.emitter_siren or "",
                    emitter_siret=parsed.emitter_siret,
                    emitter_name=parsed.emitter_name,
                    invoice_number=parsed.invoice_number or flow_id,
                    invoice_date=parsed.invoice_date or _to_date(flow.get("submitted_at")),
                    invoice_type=invoice_type_from_code(parsed.type_code),
                    amount_total=parsed.amount_total,
                    amount_excl_tax=parsed.amount_excl_tax,
                    currency=parsed.currency or "EUR",
                    syntax=flow_syntax or "Factur-X",
                    processing_rule=metadata.get("processingRule", "B2B"),
                    afnor_api_version=core.AFNOR_API_VERSION,
                    superpdp_submitted_at=flow.get("submitted_at"),
                    superpdp_updated_at=flow.get("updated_at"),
                    file_name=metadata.get("name") or f"{flow_id}.xml",
                    file_content=file_content,
                    raw_metadata=metadata,
                    flow_profile=metadata.get("flowProfile"),
                    processing_rule_source=metadata.get("processingRuleSource"),
                    tracking_id=metadata.get("trackingId"),
                    flow_direction=metadata.get("flow_direction") or metadata.get("flowDirection"),
                    flow_type=metadata.get("flowType"),
                    flow_name=metadata.get("name"),
                    ack_status=metadata.get("state"),
                    ack_details=ack_details or None,
                )
            )
        return invoices
