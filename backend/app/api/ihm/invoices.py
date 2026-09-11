import os
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.afnor.client.base import RawInvoice
from app.afnor.client.fake import FakeSuperPDPClient
from app.auth.perimeter import apply_company_scope, ensure_company_in_scope
from app.auth.session import get_current_user
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.referential import Company, PartnerDirectory, User
from app.models.invoicing import Invoice
from app.models.lifecycle import LifecycleEvent
from app.schemas.invoice import InvoiceDetailRead, InvoiceRead, SimulateInvoiceReception
from app.schemas.lifecycle import CreateManualLifecycleEvent, LifecycleEventRead
from app.services import audit_trace_service
from app.services.invoice_ingestion_service import ingest_from_client
from app.services.lifecycle_service import LifecycleValidationError, ManualEventInput, create_manual_event

router = APIRouter()

INVOICE_DOWNLOAD_ACTION = "invoice_download"


def _last_download(db: Session, invoice_id: int) -> tuple[object | None, str | None]:
    """Dernier téléchargement de cette facture, obtenu par jointure sur `AuditLog`
    (§ 6.1) — jamais dénormalisé sur `Invoice`."""
    last = (
        db.query(AuditLog)
        .filter(AuditLog.action == INVOICE_DOWNLOAD_ACTION, AuditLog.target == str(invoice_id))
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    if last is None:
        return None, None
    user_email = None
    if last.user_id is not None:
        user = db.get(User, last.user_id)
        user_email = user.email if user else None
    return last.created_at, user_email


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
    user: User | None = Depends(get_current_user),
):
    """Consultation des factures avec filtrage riche (§ 8.3) — restreinte au périmètre
    entreprises de l'utilisateur (§ NF4)."""
    query = apply_company_scope(db.query(Invoice), user=user, company_id_column=Invoice.company_id)
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
def get_invoice(
    invoice_id: int, db: Session = Depends(get_db), user: User | None = Depends(get_current_user)
):
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    ensure_company_in_scope(user, invoice.company_id)

    emitter_name = None
    if invoice.partner_directory_id is not None:
        # Raison sociale de l'émetteur obtenue par jointure, jamais dénormalisée (§ 6.1).
        partner = db.get(PartnerDirectory, invoice.partner_directory_id)
        emitter_name = partner.name if partner else None

    data = InvoiceDetailRead.model_validate(invoice)
    data.emitter_name = emitter_name
    data.last_download_at, data.last_download_by = _last_download(db, invoice.id)
    return data


@router.get("/{invoice_id}/download")
def download_invoice(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Téléchargement du fichier de la facture (§ 4.2/§ 8.3) — chaque téléchargement
    génère une entrée `AuditLog` (NF9), consultée par jointure sur la fiche facture."""
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    ensure_company_in_scope(user, invoice.company_id)

    if not os.path.exists(invoice.file_path):
        raise HTTPException(status_code=404, detail="Invoice file not found on disk")

    audit_trace_service.record_audit_log(
        db,
        action=INVOICE_DOWNLOAD_ACTION,
        target=str(invoice.id),
        user_id=user.id if user else None,
        ip_address=request.client.host if request.client else None,
    )

    return FileResponse(
        invoice.file_path,
        filename=os.path.basename(invoice.file_path),
        media_type="application/octet-stream",
    )


@router.get("/{invoice_id}/lifecycle-events", response_model=list[LifecycleEventRead])
def list_lifecycle_events(
    invoice_id: int, db: Session = Depends(get_db), user: User | None = Depends(get_current_user)
):
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    ensure_company_in_scope(user, invoice.company_id)
    return (
        db.query(LifecycleEvent)
        .filter(LifecycleEvent.invoice_id == invoice_id)
        .order_by(LifecycleEvent.event_datetime.desc())
        .all()
    )


@router.post("/{invoice_id}/lifecycle-events", response_model=LifecycleEventRead, status_code=201)
def create_lifecycle_event(
    invoice_id: int,
    payload: CreateManualLifecycleEvent,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Saisie manuelle d'un statut de cycle de vie (§ 4.2). Toujours côté achat : seule
    la fiche d'une facture reçue existe comme point d'entrée IHM (cf. LifecycleService)."""
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    ensure_company_in_scope(user, invoice.company_id)

    try:
        return create_manual_event(
            db,
            invoice=invoice,
            side="purchase",
            data=ManualEventInput(
                status=payload.status,
                reason=payload.reason,
                action=payload.action,
                comment=payload.comment,
                confirmed=payload.confirmed,
            ),
        )
    except LifecycleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/simulate", response_model=InvoiceRead, status_code=201)
def simulate_invoice_reception(
    payload: SimulateInvoiceReception,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Simule la réception d'une facture (dev/tests) via le client AFNOR fake, en
    attendant le vrai polling SuperPDP (§ 4.1, lot 5/6)."""
    ensure_company_in_scope(user, payload.company_id)
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
