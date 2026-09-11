"""API AFNOR XP Z12-013 exposée à Odoo — version v1 (spec.md § 4.4/§ 4.8).

Point d'entrée du registre de versions (`app/afnor/versioning/`) : une future v2
serait un module frère, monté sur un autre préfixe, sans toucher à celui-ci."""

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.oauth import get_current_oauth_application, issue_access_token, verify_secret
from app.config import settings
from app.db.session import get_db
from app.models.referential import OAuthApplication
from app.schemas.invoice import InvoiceRead
from app.schemas.oauth import DirectoryLookupRead, TokenResponse
from app.services import afnor_server_controller, audit_trace_service

AFNOR_API_VERSION = "v1"

router = APIRouter()


@router.post("/oauth/token", response_model=TokenResponse)
def issue_token(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    db: Session = Depends(get_db),
):
    if grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="unsupported_grant_type")

    oauth_app = db.query(OAuthApplication).filter(OAuthApplication.client_id == client_id).first()
    if oauth_app is None or not verify_secret(client_secret, oauth_app.client_secret_hash):
        raise HTTPException(status_code=401, detail="invalid_client")

    token = issue_access_token(oauth_app)
    response = TokenResponse(access_token=token, expires_in=settings.jwt_expiry_seconds)
    audit_trace_service.record_flow_trace(
        db,
        direction="odoo_to_router",
        afnor_api_version=AFNOR_API_VERSION,
        request={"endpoint": "POST /oauth/token", "client_id": client_id},
        response={"status": "issued"},
        http_status=200,
    )
    return response


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
