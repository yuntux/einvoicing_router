"""Job de polling périodique (spec.md § 4.1, lot 6) — déclencheur découplé introduit
au lot 2 (`InvoiceIngestionService.ingest_from_client`), enfin branché sur le
scheduler définitif plutôt qu'appelé uniquement via `/invoices/simulate` (dev/tests).

Chaque cycle par entreprise est tracé dans `TechnicalLog` (§ 6.1, lot 8) : c'est
exactement l'exemple de "cron de récupération" donné par la spec pour ce journal —
résultat métier (compteurs, succès/échec), complémentaire du détail HTTP brut que
`FlowTrace` capture déjà au niveau du client AFNOR."""

from sqlalchemy.orm import Session

from app.models.referential import Company
from app.services import audit_trace_service
from app.services.client_factory import resolve_client_for_company
from app.services.invoice_ingestion_service import ingest_from_client

LOG_TYPE = "invoice_polling"
LOG_ORIGIN = "scheduler"


def run_polling_cycle(db: Session) -> None:
    for company in db.query(Company).order_by(Company.id).all():
        try:
            client = resolve_client_for_company(db, company)
            result = ingest_from_client(db, company=company, client=client)
        except Exception as exc:
            audit_trace_service.record_technical_log(
                db,
                log_type=LOG_TYPE,
                origin=LOG_ORIGIN,
                company_id=company.id,
                status="error",
                details=str(exc),
            )
            # Une entreprise mal configurée (pas d'identifiants SuperPDP, § 4.10) ne
            # doit pas empêcher le polling des autres entreprises gérées.
            continue

        audit_trace_service.record_technical_log(
            db,
            log_type=LOG_TYPE,
            origin=LOG_ORIGIN,
            company_id=company.id,
            status="warning" if result.unrouted_invoice_ids else "success",
            new_count=len(result.created),
            updated_count=len(result.updated),
        )
