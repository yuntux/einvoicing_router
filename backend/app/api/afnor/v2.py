"""API AFNOR XP Z12-013 exposée à Odoo — version v2 (spec.md § 4.4/§ 4.8, lot 8).

Preuve du registre de versions (`app/afnor/versioning/registry.py`) : ce module
réutilise `AfnorServerController`, `AuditTraceService` et l'authentification OAuth
exactement comme `v1.py`, sans qu'aucun de ces services n'ait été modifié pour
l'occasion — seul un nouveau router est ajouté et monté sur un préfixe distinct
(`/api/afnor/v2`, § 4.8 : "routage par préfixe d'URL"). En pratique, tant que la norme
XP Z12-013 n'a pas de v2 publiée, ce module expose la même surface que v1 ; il
matérialise le point d'extension plutôt qu'un changement de comportement réel."""

from fastapi import APIRouter, Depends, HTTPException

from app.afnor.client.adapter import afnor_client_adapter
from app.afnor.server import afnor_server_controller
from app.afnor.versioning.registry import register_version
from app.auth.oauth import get_current_oauth_application
from app.db.session import get_db
from app.models.referential import Company, OAuthApplication
from app.schemas.invoice import InvoiceRead
from app.services import audit_trace_service
from sqlalchemy.orm import Session

AFNOR_API_VERSION = "v2"

router = APIRouter()


def _company_for(db: Session, oauth_app: OAuthApplication) -> Company:
    company = db.get(Company, oauth_app.company_id)
    if company is None:
        raise HTTPException(status_code=500, detail="Application OAuth sans entreprise associée")
    return company


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


@router.get("/directory/{siren}")
def lookup_directory(
    siren: str,
    oauth_app: OAuthApplication = Depends(get_current_oauth_application),
    db: Session = Depends(get_db),
):
    """Proxy transparent de consultation d'annuaire (§ 4.4) : la réponse de SuperPDP est
    retransmise telle quelle à Odoo, sans création de `PartnerDirectory` ni de règle de
    routage implicite (cf. `v1.lookup_directory`)."""
    company = _company_for(db, oauth_app)

    try:
        result = afnor_client_adapter.lookup_directory_siren(
            db, company=company, siren=siren, afnor_api_version=AFNOR_API_VERSION
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SuperPDP unreachable: {exc}") from exc

    audit_trace_service.record_flow_trace(
        db,
        direction="odoo_to_router",
        afnor_api_version=AFNOR_API_VERSION,
        request={"endpoint": "GET /directory/{siren}", "siren": siren, "client_id": oauth_app.client_id},
        response=result,
        http_status=200,
    )
    return result


register_version(AFNOR_API_VERSION, router)
