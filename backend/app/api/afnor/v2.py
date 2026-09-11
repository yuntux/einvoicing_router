"""API AFNOR XP Z12-013 exposée à Odoo — version v2 (spec.md § 4.4/§ 4.8, lot 8).

Preuve du registre de versions (`app/afnor/versioning/registry.py`) : ce module
réutilise `AfnorServerController`, `AuditTraceService` et l'authentification OAuth
exactement comme `v1.py`, sans qu'aucun de ces services n'ait été modifié pour
l'occasion — seul un nouveau router est ajouté et monté sur un préfixe distinct
(`/api/afnor/v2`, § 4.8 : "routage par préfixe d'URL"). En pratique, tant que la norme
XP Z12-013 n'a pas de v2 publiée, ce module expose la même surface que v1 ; il
matérialise le point d'extension plutôt qu'un changement de comportement réel."""

from fastapi import APIRouter, Depends, Query

from app.afnor.versioning.registry import register_version
from app.auth.oauth import get_current_oauth_application
from app.db.session import get_db
from app.models.referential import OAuthApplication
from app.schemas.invoice import InvoiceRead
from app.schemas.oauth import DirectoryLookupRead
from app.services import afnor_server_controller, audit_trace_service
from sqlalchemy.orm import Session

AFNOR_API_VERSION = "v2"

router = APIRouter()


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


register_version(AFNOR_API_VERSION, router)
