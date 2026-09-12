"""Routes communes à toutes les versions de l'API AFNOR exposée à Odoo (§ 4.4/§ 4.8) :
`GET /invoices` et `GET /directory/{siren}` sont identiques quelle que soit la version
tant que XP Z12-013 n'a pas publié de v2 réelle — `v1.py` les enregistre en plus de ses
routes propres (`/oauth/token`, `/invoices/emit`, `/lifecycle-events/emit`), `v2.py` les
enregistre seules (§ 4.8, "point d'extension" du registre de versions)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.afnor.client.adapter import afnor_client_adapter
from app.afnor.server import afnor_server_controller
from app.afnor.server.afnor_server_controller import call_superpdp
from app.auth.oauth import get_current_oauth_application
from app.db.session import get_db
from app.models.referential import Company, OAuthApplication
from app.schemas.invoice import InvoiceRead
from app.services import audit_trace_service


def company_for(db: Session, oauth_app: OAuthApplication) -> Company:
    company = db.get(Company, oauth_app.company_id)
    if company is None:
        raise HTTPException(status_code=500, detail="Application OAuth sans entreprise associée")
    return company


def register_common_routes(router: APIRouter, afnor_api_version: str) -> None:
    @router.get("/invoices", response_model=list[InvoiceRead])
    def list_invoices(
        request: Request,
        oauth_app: OAuthApplication = Depends(get_current_oauth_application),
        db: Session = Depends(get_db),
    ):
        invoices = afnor_server_controller.list_invoices_for_consumer(db, oauth_app=oauth_app)
        audit_trace_service.record_odoo_flow_trace(
            db,
            request,
            afnor_api_version=afnor_api_version,
            endpoint="GET /invoices",
            client_id=oauth_app.client_id,
            response={"count": len(invoices)},
            http_status=200,
        )
        return invoices

    @router.get("/directory/{siren}")
    def lookup_directory(
        siren: str,
        request: Request,
        oauth_app: OAuthApplication = Depends(get_current_oauth_application),
        db: Session = Depends(get_db),
    ):
        """Proxy transparent de consultation d'annuaire (§ 4.4) : la réponse de SuperPDP
        est retransmise telle quelle à Odoo — aucune création de `PartnerDirectory` ni de
        règle de routage implicite, l'annuaire consulté par Odoo concerne ses propres
        clients, pas les fournisseurs dont le routeur gère le routage (§ 4.3)."""
        company = company_for(db, oauth_app)

        result = call_superpdp(
            lambda: afnor_client_adapter.lookup_directory_siren(
                db, company=company, siren=siren, afnor_api_version=afnor_api_version
            )
        )

        audit_trace_service.record_odoo_flow_trace(
            db,
            request,
            afnor_api_version=afnor_api_version,
            endpoint="GET /directory/{siren}",
            siren=siren,
            client_id=oauth_app.client_id,
            response=result,
            http_status=200,
        )
        return result
