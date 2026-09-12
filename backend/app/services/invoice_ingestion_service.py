"""InvoiceIngestionService — stockage + indexation + routage effectif des factures
reçues (spec.md § 4.1, § 4.3)."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.afnor.client.base import RawInvoice, SuperPDPClientProtocol
from app.models.referential import Company, PartnerDirectory
from app.models.invoicing import Invoice, InvoiceRouting
from app.services import directory_service, retry_scheduler_service, routing_rule_service
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

    received_at = datetime.utcnow()
    file_path = save_invoice_file(
        company_siren=company.siren,
        flow_id=raw.superpdp_flow_id,
        file_name=raw.file_name,
        content=raw.file_content,
        received_at=received_at,
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
        received_at=received_at,
        flow_profile=raw.flow_profile,
        processing_rule_source=raw.processing_rule_source,
        tracking_id=raw.tracking_id,
        flow_direction=raw.flow_direction,
        flow_type=raw.flow_type,
        flow_name=raw.flow_name,
        ack_status=raw.ack_status,
        ack_details=raw.ack_details,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice, True


def _placeholder_partner_name(siren: str) -> str:
    return f"Fournisseur {siren} (à compléter)"


def _ensure_partner(
    db: Session, invoice: Invoice, *, emitter_name: str | None = None
) -> tuple[PartnerDirectory, bool]:
    """Rattache la facture à son émetteur dans l'annuaire (§ 4.4), en le créant s'il
    est inconnu jusque-là. `emitter_name` (raison sociale portée par le flux AFNOR,
    cf. `RawInvoice.emitter_name`) est utilisé quand disponible ; sinon un placeholder,
    à corriger depuis l'IHM. Si un fournisseur existant n'a encore que ce placeholder
    et qu'un nom nous parvient enfin (facture suivante, flux plus complet), on le
    complète rétroactivement plutôt que de le laisser indéfiniment générique."""
    partner, created = directory_service.get_or_create_partner(
        db,
        siren=invoice.emitter_siren,
        siret=invoice.emitter_siret,
        name=emitter_name or _placeholder_partner_name(invoice.emitter_siren),
    )
    if not created and emitter_name and partner.name == _placeholder_partner_name(partner.siren):
        partner.name = emitter_name
        db.commit()
    if invoice.partner_directory_id != partner.id:
        invoice.partner_directory_id = partner.id
        db.commit()
    return partner, created


def _route_invoice(db: Session, invoice: Invoice, *, emitter_name: str | None = None) -> bool:
    """Résout et matérialise le routage effectif de la facture (§ 4.3).

    Gère aussi l'alerting associé (§ 4.7) : au premier fournisseur inconnu, crée son
    entrée d'annuaire et alerte une seule fois "nouveau fournisseur sans règle de
    routage" plutôt que l'alerte générique — sinon, alerte générique "facture non
    routée", elle aussi envoyée une seule fois par facture (`unrouted_alert_sent`)
    pour ne jamais spammer les Gestionnaires de facturation à chaque cycle de polling.

    Retourne True si la facture n'a résolu aucune cible."""
    partner, partner_created = _ensure_partner(db, invoice, emitter_name=emitter_name)

    targets = routing_rule_service.resolve(
        db,
        siren=invoice.emitter_siren,
        company_id=invoice.company_id,
    )
    existing_target_ids = {r.target_application_id for r in invoice.routings}
    for target in targets:
        if target.id in existing_target_ids:
            continue
        db.add(InvoiceRouting(invoice_id=invoice.id, target_application_id=target.id))
    db.commit()

    if targets:
        return False

    if partner_created:
        retry_scheduler_service.alert_new_partner_without_routing_rule(db, partner=partner)
        invoice.unrouted_alert_sent = True
        db.commit()
    elif not invoice.unrouted_alert_sent:
        retry_scheduler_service.alert_unrouted_invoice(db, invoice=invoice)
        invoice.unrouted_alert_sent = True
        db.commit()
    return True


def reroute_unrouted_invoices_for_partner(
    db: Session, *, partner_directory_id: int, target_application_id: int
) -> int:
    """Route vers `target_application_id` les factures déjà reçues de ce fournisseur
    qui n'y sont pas encore routées (§ 4.3) — appelée quand une règle de routage
    vient d'être activée pour ce couple (cf. `app.api.ihm.routing_rules`), pour ne
    pas attendre le prochain cycle de polling. Scopé à cette seule cible : une
    facture déjà routée vers une autre application n'est pas ignorée pour autant,
    seul le manque vis-à-vis de `target_application_id` est comblé.
    Retourne le nombre de factures nouvellement routées."""
    candidates = (
        db.query(Invoice)
        .filter(Invoice.partner_directory_id == partner_directory_id)
        .all()
    )
    rerouted = 0
    for invoice in candidates:
        existing_target_ids = {r.target_application_id for r in invoice.routings}
        if target_application_id in existing_target_ids:
            continue
        db.add(InvoiceRouting(invoice_id=invoice.id, target_application_id=target_application_id))
        rerouted += 1
    db.commit()
    return rerouted


def ingest_from_client(
    db: Session,
    *,
    company: Company,
    client: SuperPDPClientProtocol,
    since: datetime | None = None,
) -> IngestResult:
    raw_invoices = client.fetch_received_invoices(company_siren=company.siren, since=since)

    created: list[Invoice] = []
    updated: list[Invoice] = []
    unrouted_ids: list[int] = []

    for raw in raw_invoices:
        invoice, is_new = _upsert_invoice(db, company, raw)
        (created if is_new else updated).append(invoice)
        if _route_invoice(db, invoice, emitter_name=raw.emitter_name):
            unrouted_ids.append(invoice.id)

    return IngestResult(created=created, updated=updated, unrouted_invoice_ids=unrouted_ids)
