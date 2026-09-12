"""Ingestion des CDAR entrants (spec.md § 4.2, § 4.1 pour le déclencheur de polling
partagé) : rattache chaque message de cycle de vie reçu (flux `SupplierInvoiceLC`) à la
facture existante correspondante, sans jamais créer de nouvelle `Invoice` à partir de
ce type de flux — cf. l'incident du flux ie_78332 (§ scheduler/polling_job.py)."""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.afnor.client.base import CertifiedPlatformClientProtocol
from app.models.invoicing import Invoice
from app.models.lifecycle import LifecycleEvent
from app.models.referential import Company
from app.services import cdar_service, lifecycle_service


@dataclass
class IngestLifecycleResult:
    created: list[LifecycleEvent] = field(default_factory=list)
    # Facture introuvable pour le numéro porté par le CDAR (MDT-87) — ex. reçu avant
    # que la facture elle-même n'ait été ingérée, ou hors périmètre de l'entreprise.
    unmatched_flow_ids: list[str] = field(default_factory=list)
    # CDAR non exploitable (XML invalide, échec de validation XSD...).
    failed_flow_ids: list[str] = field(default_factory=list)


def ingest_incoming_lifecycle_events(
    db: Session,
    *,
    company: Company,
    client: CertifiedPlatformClientProtocol,
    since: datetime | None = None,
) -> IngestLifecycleResult:
    result = IngestLifecycleResult()
    raw_cdars = client.fetch_incoming_lifecycle_events(company_siren=company.siren, since=since)

    for raw in raw_cdars:
        try:
            parsed = cdar_service.parse(raw.xml_bytes)
        except Exception:
            result.failed_flow_ids.append(raw.flow_id)
            continue

        invoice_number = parsed.get("invoice_number")
        invoice = (
            db.query(Invoice)
            .filter(Invoice.company_id == company.id, Invoice.invoice_number == invoice_number)
            .first()
            if invoice_number
            else None
        )
        if invoice is None:
            result.unmatched_flow_ids.append(raw.flow_id)
            continue

        event = lifecycle_service.create_incoming_event(
            db,
            invoice=invoice,
            flow_id=raw.flow_id,
            xml_bytes=raw.xml_bytes,
            parsed=parsed,
            flow_type=raw.flow_type,
        )
        if event is not None:
            result.created.append(event)

    return result
