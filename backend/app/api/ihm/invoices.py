import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import Integer, cast
from sqlalchemy.orm import Session

from app.auth.perimeter import apply_company_scope, ensure_company_in_scope
from app.auth.session import get_current_user, require_write
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.referential import Company, PartnerDirectory, User
from app.models.invoicing import Invoice
from app.models.lifecycle import AfnorFlow, LifecycleEvent, LifecycleEventAttachment
from app.schemas.invoice import InvoiceDetailRead, InvoiceRead
from app.schemas.lifecycle import (
    AfnorFlowRead,
    CreateManualLifecycleEvent,
    LifecycleEventAttachmentRead,
    LifecycleEventPaymentRead,
    LifecycleEventRead,
)
from app.services import audit_trace_service
from app.services.lifecycle_service import LifecycleValidationError, ManualEventInput, create_manual_event

router = APIRouter()

INVOICE_DOWNLOAD_ACTION = "invoice_download"


def _afnor_flow_to_read(flow: AfnorFlow) -> AfnorFlowRead:
    return AfnorFlowRead(
        id=flow.id,
        flow_id=flow.flow_id,
        direction=flow.direction,
        flow_type=flow.flow_type,
        syntax=flow.syntax,
        processing_rule=flow.processing_rule,
        state=flow.state,
        has_file=flow.file_bin is not None,
    )


def _lifecycle_event_to_read(event: LifecycleEvent) -> LifecycleEventRead:
    """Construction explicite (§ schemas/lifecycle.py) : `attachments`/`payments`
    mêlent un champ dérivé (`has_file`) que la conversion `from_attributes`
    automatique ne sait pas produire."""
    return LifecycleEventRead(
        id=event.id,
        invoice_id=event.invoice_id,
        event_datetime=event.event_datetime,
        status=event.status,
        direction=event.direction,
        amount=event.amount,
        currency=event.currency,
        details=[
            {"reason": d.reason, "action": d.action, "comment": d.comment} for d in event.details
        ],
        payments=[LifecycleEventPaymentRead.model_validate(p) for p in event.payments],
        attachments=[
            LifecycleEventAttachmentRead(id=a.id, filename=a.filename, has_file=bool(a.file_path))
            for a in event.attachments
        ],
        afnor_flow=_afnor_flow_to_read(event.afnor_flow) if event.afnor_flow is not None else None,
    )


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
    user_label = None
    if last.user_id is not None:
        user = db.get(User, last.user_id)
        user_label = (user.name or user.email) if user else None
    return last.created_at, user_label


def _last_downloads_bulk(
    db: Session, invoice_ids: list[int]
) -> dict[int, tuple[object, str | None]]:
    """Équivalent de `_last_download` pour une liste de factures (§ 8.3, colonne
    "Dernier téléchargement" de la liste) — une seule requête plutôt qu'un aller-
    retour AuditLog par ligne affichée."""
    if not invoice_ids:
        return {}
    logs = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == INVOICE_DOWNLOAD_ACTION,
            AuditLog.target.in_([str(i) for i in invoice_ids]),
        )
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    user_cache: dict[int, str | None] = {}
    result: dict[int, tuple[object, str | None]] = {}
    for log in logs:
        user_label = None
        if log.user_id is not None:
            if log.user_id not in user_cache:
                user = db.get(User, log.user_id)
                user_cache[log.user_id] = (user.name or user.email) if user else None
            user_label = user_cache[log.user_id]
        # Tri croissant : la dernière itération pour un même invoice_id est bien la
        # plus récente, elle écrase les précédentes.
        result[int(log.target)] = (log.created_at, user_label)
    return result


def _emitter_names_bulk(db: Session, sirens: set[str]) -> dict[str, str | None]:
    """Raison sociale de chaque émetteur (§ 6.1), par SIREN — une seule requête
    plutôt qu'un aller-retour `PartnerDirectory` par facture affichée. Un SIREN peut
    porter plusieurs entrées d'annuaire (SIRET différents) : on ne garde que la
    première rencontrée, purement indicatif pour l'affichage de liste (le détail
    d'une facture, lui, résout la véritable entrée liée via `partner_directory_id`)."""
    if not sirens:
        return {}
    names: dict[str, str | None] = {}
    for partner in db.query(PartnerDirectory).filter(PartnerDirectory.siren.in_(sirens)).all():
        names.setdefault(partner.siren, partner.name)
    return names


def _company_names_bulk(db: Session, company_ids: set[int]) -> dict[int, tuple[str, str]]:
    """Raison sociale et SIREN de chaque entreprise réceptrice (§ 6.1), par id —
    sans passer par `/companies/lookup` (qui masque volontairement le SIREN pour un
    affichage inter-entreprises, § 5.1) : ici, `apply_company_scope` garantit déjà
    que les factures listées appartiennent au périmètre de l'utilisateur, donc
    afficher le SIREN de *sa propre* entreprise réceptrice n'expose rien hors
    périmètre."""
    if not company_ids:
        return {}
    return {
        company.id: (company.name, company.siren)
        for company in db.query(Company).filter(Company.id.in_(company_ids)).all()
    }


@router.get("", response_model=list[InvoiceRead])
def list_invoices(
    company_id: int | None = None,
    emitter_siren: str | None = None,
    emitter_name: str | None = None,
    invoice_number: str | None = None,
    syntax: str | None = None,
    processing_rule: str | None = None,
    invoice_date_from: date | None = None,
    invoice_date_to: date | None = None,
    amount_excl_tax_min: float | None = None,
    amount_excl_tax_max: float | None = None,
    vat_amount_min: float | None = None,
    vat_amount_max: float | None = None,
    amount_total_min: float | None = None,
    amount_total_max: float | None = None,
    downloaded: bool | None = None,
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
    if emitter_name is not None:
        # Raison sociale non dénormalisée sur Invoice (§ 6.1) : recherche par
        # sous-requête sur PartnerDirectory, jamais par jointure directe (un même
        # SIREN peut porter plusieurs entrées d'annuaire — SIRET différents —, ce qui
        # dupliquerait les lignes de factures avec une jointure classique).
        query = query.filter(
            Invoice.emitter_siren.in_(
                db.query(PartnerDirectory.siren).filter(
                    PartnerDirectory.name.ilike(f"%{emitter_name}%")
                )
            )
        )
    if invoice_number is not None:
        query = query.filter(Invoice.invoice_number.contains(invoice_number))
    if syntax is not None:
        query = query.filter(Invoice.syntax == syntax)
    if processing_rule is not None:
        query = query.filter(Invoice.processing_rule == processing_rule)
    if invoice_date_from is not None:
        query = query.filter(Invoice.invoice_date >= invoice_date_from)
    if invoice_date_to is not None:
        query = query.filter(Invoice.invoice_date <= invoice_date_to)
    if amount_excl_tax_min is not None:
        query = query.filter(Invoice.amount_excl_tax >= amount_excl_tax_min)
    if amount_excl_tax_max is not None:
        query = query.filter(Invoice.amount_excl_tax <= amount_excl_tax_max)
    if vat_amount_min is not None:
        query = query.filter((Invoice.amount_total - Invoice.amount_excl_tax) >= vat_amount_min)
    if vat_amount_max is not None:
        query = query.filter((Invoice.amount_total - Invoice.amount_excl_tax) <= vat_amount_max)
    if amount_total_min is not None:
        query = query.filter(Invoice.amount_total >= amount_total_min)
    if amount_total_max is not None:
        query = query.filter(Invoice.amount_total <= amount_total_max)
    if downloaded is not None:
        # Statut de téléchargement obtenu par jointure sur AuditLog (§ 6.1), jamais
        # dénormalisé sur Invoice — AuditLog.target stocke str(invoice_id).
        downloaded_ids = db.query(cast(AuditLog.target, Integer)).filter(
            AuditLog.action == INVOICE_DOWNLOAD_ACTION
        )
        if downloaded:
            query = query.filter(Invoice.id.in_(downloaded_ids))
        else:
            query = query.filter(~Invoice.id.in_(downloaded_ids))
    invoices = list(query.order_by(Invoice.received_at.desc()).all())

    downloads = _last_downloads_bulk(db, [invoice.id for invoice in invoices])
    emitter_names = _emitter_names_bulk(db, {invoice.emitter_siren for invoice in invoices})
    company_names = _company_names_bulk(db, {invoice.company_id for invoice in invoices})
    results = []
    for invoice in invoices:
        data = InvoiceRead.model_validate(invoice)
        data.last_download_at, data.last_download_by = downloads.get(invoice.id, (None, None))
        data.emitter_name = emitter_names.get(invoice.emitter_siren)
        company_name, company_siren = company_names.get(invoice.company_id, (None, None))
        data.company_name = company_name
        data.company_siren = company_siren
        results.append(data)
    return results


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

    company = db.get(Company, invoice.company_id)

    flows = (
        db.query(AfnorFlow)
        .filter(AfnorFlow.invoice_id == invoice_id)
        .order_by(AfnorFlow.id)
        .all()
    )

    data = InvoiceDetailRead.model_validate(invoice)
    data.emitter_name = emitter_name
    data.company_name = company.name if company else None
    data.company_siren = company.siren if company else None
    data.last_download_at, data.last_download_by = _last_download(db, invoice.id)
    data.afnor_flows = [_afnor_flow_to_read(flow) for flow in flows]
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

    audit_trace_service.record_user_action(
        db, request, user, action=INVOICE_DOWNLOAD_ACTION, target=str(invoice.id)
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
    events = (
        db.query(LifecycleEvent)
        .filter(LifecycleEvent.invoice_id == invoice_id)
        .order_by(LifecycleEvent.event_datetime.desc())
        .all()
    )
    return [_lifecycle_event_to_read(event) for event in events]


@router.get("/{invoice_id}/lifecycle-events/{event_id}/attachments/{attachment_id}/download")
def download_lifecycle_event_attachment(
    invoice_id: int,
    event_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Pièce jointe d'un événement de cycle de vie (§ 6.2) — jamais exposée
    autrement que par ce téléchargement explicite."""
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    ensure_company_in_scope(user, invoice.company_id)

    attachment = db.get(LifecycleEventAttachment, attachment_id)
    if attachment is None or attachment.event_id != event_id or attachment.event.invoice_id != invoice_id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if not attachment.file_path or not os.path.exists(attachment.file_path):
        raise HTTPException(status_code=404, detail="Attachment file not found on disk")

    return FileResponse(
        attachment.file_path,
        filename=attachment.filename,
        media_type="application/octet-stream",
    )


@router.get("/{invoice_id}/afnor-flows/{flow_id}/download")
def download_afnor_flow(
    invoice_id: int,
    flow_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Contenu brut d'un flux AFNOR (CDAR/facture générée, § 6.2) — jamais exposé
    autrement que par ce téléchargement explicite."""
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    ensure_company_in_scope(user, invoice.company_id)

    flow = db.get(AfnorFlow, flow_id)
    if flow is None or flow.invoice_id != invoice_id:
        raise HTTPException(status_code=404, detail="AFNOR flow not found")
    if flow.file_bin is None:
        raise HTTPException(status_code=404, detail="AFNOR flow has no file")

    return Response(
        content=flow.file_bin,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="afnor-flow-{flow.id}.xml"'},
    )


@router.post(
    "/{invoice_id}/lifecycle-events",
    response_model=LifecycleEventRead,
    status_code=201,
    dependencies=[Depends(require_write)],
)
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
        event = create_manual_event(
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
    return _lifecycle_event_to_read(event)
