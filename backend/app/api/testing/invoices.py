import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.afnor.client.base import RawInvoice
from app.afnor.client.fake import FakeSuperPDPClient
from app.db.session import get_db
from app.models.referential import Company
from app.schemas.invoice import InvoiceRead, SimulateInvoiceReception
from app.services.invoice_ingestion_service import ingest_from_client

# Point d'entrée réservé aux tests (pytest/Playwright) : jamais monté en production
# (cf. app/main.py, monté uniquement si settings.superpdp_client_mode == "fake") — la
# réception réelle d'une facture passe exclusivement par le polling SuperPDP (§ 4.1).
router = APIRouter()


@router.post("/invoices/simulate", response_model=InvoiceRead, status_code=201)
def simulate_invoice_reception(payload: SimulateInvoiceReception, db: Session = Depends(get_db)):
    company = db.get(Company, payload.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    raw = RawInvoice(
        superpdp_flow_id=f"sim-{uuid.uuid4().hex[:12]}",
        emitter_siren=payload.emitter_siren,
        emitter_siret=payload.emitter_siret,
        emitter_name=payload.emitter_name,
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
