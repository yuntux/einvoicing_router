"""API AFNOR XP Z12-013 exposée à Odoo — version v1 (spec.md § 4.4/§ 4.8).

Point d'entrée du registre de versions (`app/afnor/versioning/registry.py`) : `v2`
(module frère `app/api/afnor/v2.py`) est monté sur un autre préfixe sans toucher à
celui-ci ni aux services qu'il appelle."""

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.afnor.client.adapter import afnor_client_adapter
from app.afnor.versioning.registry import register_version
from app.auth.oauth import get_current_oauth_application, issue_token_response
from app.db.session import get_db
from app.models.referential import Company, OAuthApplication
from app.schemas.invoice import InvoiceRead
from app.schemas.oauth import DirectoryLookupRead
from app.services import afnor_server_controller, audit_trace_service

AFNOR_API_VERSION = "v1"

router = APIRouter()


def _company_for(db: Session, oauth_app: OAuthApplication) -> Company:
    company = db.get(Company, oauth_app.company_id)
    if company is None:
        raise HTTPException(status_code=500, detail="Application OAuth sans entreprise associée")
    return company


@router.post("/oauth/token")
def issue_token(
    response: Response,
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    db: Session = Depends(get_db),
):
    """Conformité RFC 6749 (authentification client, validation du grant, erreurs
    normalisées) déléguée à Authlib — cf. `app.auth.oauth.issue_token_response`."""
    status_code, body = issue_token_response(
        db, grant_type=grant_type, client_id=client_id, client_secret=client_secret
    )
    response.status_code = status_code
    audit_trace_service.record_flow_trace(
        db,
        direction="odoo_to_router",
        afnor_api_version=AFNOR_API_VERSION,
        request={"endpoint": "POST /oauth/token", "client_id": client_id},
        response={"status": "issued" if status_code == 200 else body.get("error")},
        http_status=status_code,
    )
    return body


@router.get("/invoices", response_model=list[InvoiceRead])
def list_invoices(
    oauth_app: OAuthApplication = Depends(get_current_oauth_application),
    db: Session = Depends(get_db),
):
    invoices = afnor_server_controller.list_invoices_for_consumer(db, oauth_app=oauth_app)
    audit_trace_service.record_flow_trace(
        db,
        direction="odoo_to_router",
        afnor_api_version=AFNOR_API_VERSION,
        request={"endpoint": "GET /invoices", "client_id": oauth_app.client_id},
        response={"count": len(invoices)},
        http_status=200,
    )
    return invoices


@router.get("/directory/{siren}", response_model=DirectoryLookupRead)
def lookup_directory(
    siren: str,
    name: str | None = Query(default=None),
    oauth_app: OAuthApplication = Depends(get_current_oauth_application),
    db: Session = Depends(get_db),
):
    result = afnor_server_controller.lookup_or_create_directory_entry(
        db, oauth_app=oauth_app, siren=siren, name=name
    )
    audit_trace_service.record_flow_trace(
        db,
        direction="odoo_to_router",
        afnor_api_version=AFNOR_API_VERSION,
        request={"endpoint": "GET /directory/{siren}", "siren": siren, "client_id": oauth_app.client_id},
        response={"created": result.created},
        http_status=200,
    )
    return result


@router.post("/invoices/emit")
async def emit_invoice(
    file: UploadFile,
    flow_syntax: str = Form(...),
    processing_rule: str = Form(...),
    oauth_app: OAuthApplication = Depends(get_current_oauth_application),
    db: Session = Depends(get_db),
):
    """Proxy transparent d'émission (§ 4.4) : la facture émise par Odoo est transmise
    telle quelle à SuperPDP et jamais stockée côté routeur (§ 4.1 : seules les factures
    *reçues* sont indexées) — seul le `FlowTrace` de l'échange est conservé."""
    company = _company_for(db, oauth_app)
    correlation_id = str(uuid.uuid4())
    file_bin = await file.read()

    audit_trace_service.record_flow_trace(
        db,
        direction="odoo_to_router",
        afnor_api_version=AFNOR_API_VERSION,
        request={
            "endpoint": "POST /invoices/emit",
            "filename": file.filename,
            "flow_syntax": flow_syntax,
            "processing_rule": processing_rule,
            "client_id": oauth_app.client_id,
        },
        response={"status": "forwarding"},
        http_status=202,
        correlation_id=correlation_id,
    )

    try:
        result = afnor_client_adapter.send_invoice(
            db,
            company=company,
            file_bin=file_bin,
            filename=file.filename or "invoice.xml",
            flow_syntax=flow_syntax,
            processing_rule=processing_rule,
            correlation_id=correlation_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SuperPDP unreachable: {exc}") from exc
    return result


@router.post("/lifecycle-events/emit")
async def emit_lifecycle_event(
    file: UploadFile,
    oauth_app: OAuthApplication = Depends(get_current_oauth_application),
    db: Session = Depends(get_db),
):
    """Proxy transparent de cycle de vie (§ 4.2/§ 4.4) : un message CDAR généré par
    Odoo est transmis tel quel à SuperPDP, sans réinterprétation côté routeur.

    Limitation connue : contrairement aux messages saisis manuellement dans l'IHM du
    routeur (§ 4.2, sens achat uniquement), ce proxy ne mémorise pas le message comme
    `LifecycleEvent` — il concerne potentiellement des factures de vente qu'`Invoice`
    ne modélise pas (§ 6.1, factures reçues uniquement), et son affichage dans l'IHM du
    routeur nécessiterait un écran dédié aux factures émises, hors périmètre de ce
    lot (cf. note dans `lifecycle_service.py`)."""
    company = _company_for(db, oauth_app)
    correlation_id = str(uuid.uuid4())
    cdar_bytes = await file.read()

    audit_trace_service.record_flow_trace(
        db,
        direction="odoo_to_router",
        afnor_api_version=AFNOR_API_VERSION,
        request={
            "endpoint": "POST /lifecycle-events/emit",
            "filename": file.filename,
            "client_id": oauth_app.client_id,
        },
        response={"status": "forwarding"},
        http_status=202,
        correlation_id=correlation_id,
    )

    try:
        result = afnor_client_adapter.send_cdar(
            db,
            company=company,
            cdar_bytes=cdar_bytes,
            filename=file.filename or "cdar.xml",
            correlation_id=correlation_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SuperPDP unreachable: {exc}") from exc
    return result


register_version(AFNOR_API_VERSION, router)
