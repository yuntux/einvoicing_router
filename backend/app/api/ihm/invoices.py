import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.afnor.client.base import RawInvoice
from app.afnor.client.fake import FakeSuperPDPClient
from app.db.session import get_db
from app.models.referential import Company, PartnerDirectory
from app.models.invoicing import Invoice
from app.schemas.invoice import InvoiceDetailRead, InvoiceRead, SimulateInvoiceReception
from app.services.invoice_ingestion_service import ingest_from_client

router = APIRouter()


@router.get("", response_model=list[InvoiceRead])
def list_invoices(
    company_id: int | None = None,
    emitter_siren: str | None = None,
    invoice_number: str | None = None,
    currency: str | None = None,
    syntax: str | None = None,
    processing_rule: str | None = None,
    invoice_date_from: date | None = None,
    invoice_date_to: date | None = None,
    db: Session = Depends(get_db),
):
    """Consultation des factures avec filtrage riche (§ 8.3)."""
    query = db.query(Invoice)
    if company_id is not None:
        query = query.filter(Invoice.company_id == company_id)
    if emitter_siren is not None:
        query = query.filter(Invoice.emitter_siren == emitter_siren)
    if invoice_number is not None:
        query = query.filter(Invoice.invoice_number.contains(invoice_number))
    if currency is not None:
        query = query.filter(Invoice.currency == currency)
    if syntax is not None:
        query = query.filter(Invoice.syntax == syntax)
    if processing_rule is not None:
        query = query.filter(Invoice.processing_rule == processing_rule)
    if invoice_date_from is not None:
        query = query.filter(Invoice.invoice_date >= invoice_date_from)
    if invoice_date_to is not None:
        query = query.filter(Invoice.invoice_date <= invoice_date_to)
    return list(query.order_by(Invoice.received_at.desc()).all())


@router.get("/{invoice_id}", response_model=InvoiceDetailRead)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    emitter_name = None
    if invoice.partner_directory_id is not None:
        # Raison sociale de l'émetteur obtenue par jointure, jamais dénormalisée (§ 6.1).
        partner = db.get(PartnerDirectory, invoice.partner_directory_id)
        emitter_name = partner.name if partner else None

    data = InvoiceDetailRead.model_validate(invoice)
    data.emitter_name = emitter_name
    return data


@router.post("/simulate", response_model=InvoiceRead, status_code=201)
def simulate_invoice_reception(
    payload: SimulateInvoiceReception, db: Session = Depends(get_db)
):
    """Simule la réception d'une facture (dev/tests) via le client AFNOR fake, en
    attendant le vrai polling SuperPDP (§ 4.1, lot 5/6)."""
    company = db.get(Company, payload.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    raw = RawInvoice(
        superpdp_flow_id=f"sim-{uuid.uuid4().hex[:12]}",
        emitter_siren=payload.emitter_siren,
        emitter_siret=payload.emitter_siret,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        invoice_type=payload.invoice_type,
        amount_total=payload.amount_total,
        amount_excl_tax=payload.amount_excl_tax,
        currency=payload.currency,
        syntax=payload.syntax,
        processing_rule=payload.processing_rule,
        file_name=f"{payload.invoice_number}.txt",
        file_content=f"Facture simulée {payload.invoice_number}".encode(),
    )
    client = FakeSuperPDPClient([raw])
    result = ingest_from_client(db, company=company, client=client)
    invoice = (result.created + result.updated)[0]
    return invoice
