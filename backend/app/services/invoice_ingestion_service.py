"""InvoiceIngestionService — stockage + indexation + routage effectif des factures
reçues (spec.md § 4.1, § 4.3)."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.afnor.client.base import RawInvoice, SuperPDPClientProtocol
from app.models.referential import Company
from app.models.invoicing import Invoice, InvoiceRouting
from app.services import retry_scheduler_service, routing_rule_service
from app.storage.filesystem import save_invoice_file


@dataclass
class IngestResult:
    created: list[Invoice]
    updated: list[Invoice]
    unrouted_invoice_ids: list[int]


def _upsert_invoice(db: Session, company: Company, raw: RawInvoice) -> tuple[Invoice, bool]:
    existing = (
        db.query(Invoice)
        .filter(
            Invoice.company_id == company.id,
            Invoice.superpdp_flow_id == raw.superpdp_flow_id,
        )
        .first()
    )
    if existing is not None:
        return existing, False

    file_path = save_invoice_file(
        company_siren=company.siren,
        flow_id=raw.superpdp_flow_id,
        file_name=raw.file_name,
        content=raw.file_content,
    )

    invoice = Invoice(
        company_id=company.id,
        emitter_siren=raw.emitter_siren,
        emitter_siret=raw.emitter_siret,
        invoice_number=raw.invoice_number,
        invoice_date=raw.invoice_date,
        due_date=raw.due_date,
        invoice_type=raw.invoice_type,
        file_path=file_path,
        superpdp_flow_id=raw.superpdp_flow_id,
        superpdp_submitted_at=raw.superpdp_submitted_at,
        superpdp_updated_at=raw.superpdp_updated_at,
        amount_total=raw.amount_total,
        amount_excl_tax=raw.amount_excl_tax,
        currency=raw.currency,
        syntax=raw.syntax,
        processing_rule=raw.processing_rule,
        afnor_metadata=raw.raw_metadata,
        afnor_api_version=raw.afnor_api_version,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice, True


def _route_invoice(db: Session, invoice: Invoice) -> bool:
    """Résout et matérialise le routage effectif de la facture (§ 4.3).

    Retourne True si la facture n'a résolu aucune cible (cas "facture non routée",
    § 4.7) — l'appelant déclenche alors l'alerte email correspondante."""
    targets = routing_rule_service.resolve(
        db, siren=invoice.emitter_siren, reference_date=invoice.invoice_date
    )
    existing_target_ids = {r.target_application_id for r in invoice.routings}
    for target in targets:
        if target.id in existing_target_ids:
            continue
        db.add(InvoiceRouting(invoice_id=invoice.id, target_application_id=target.id))
    db.commit()
    return len(targets) == 0


def ingest_from_client(
    db: Session, *, company: Company, client: SuperPDPClientProtocol
) -> IngestResult:
    raw_invoices = client.fetch_received_invoices(company_siren=company.siren)

    created: list[Invoice] = []
    updated: list[Invoice] = []
    unrouted_ids: list[int] = []

    for raw in raw_invoices:
        invoice, is_new = _upsert_invoice(db, company, raw)
        (created if is_new else updated).append(invoice)
        if _route_invoice(db, invoice):
            unrouted_ids.append(invoice.id)
            retry_scheduler_service.alert_unrouted_invoice(db, invoice=invoice)

    return IngestResult(created=created, updated=updated, unrouted_invoice_ids=unrouted_ids)
