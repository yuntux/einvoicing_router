"""Job de polling périodique (spec.md § 4.1, lot 6) — déclencheur découplé introduit
au lot 2 (`InvoiceIngestionService.ingest_from_client`), enfin branché sur le
scheduler définitif plutôt qu'appelé uniquement via `/invoices/simulate` (dev/tests).

Chaque cycle par entreprise est tracé dans `TechnicalLog` (§ 6.1, lot 8) : c'est
exactement l'exemple de "cron de récupération" donné par la spec pour ce journal —
résultat métier (compteurs, succès/échec), complémentaire du détail HTTP brut que
`FlowTrace` capture déjà au niveau du client AFNOR."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.referential import Company
from app.services import audit_trace_service
from app.services.client_factory import resolve_client_for_company
from app.services.invoice_ingestion_service import ingest_from_client
from app.services.lifecycle_ingestion_service import ingest_incoming_lifecycle_events

LOG_TYPE = "invoice_polling"
LIFECYCLE_LOG_TYPE = "lifecycle_polling"
LOG_ORIGIN = "scheduler"


def run_polling_cycle(db: Session) -> None:
    for company in db.query(Company).order_by(Company.id).all():
        # Capturé avant l'appel, pas après (§ 4.1) : un flux mis à jour côté AFNOR
        # pendant l'appel lui-même doit rester couvert par le `since` du *prochain*
        # cycle plutôt que d'être manqué parce que le curseur aurait avancé trop loin.
        cycle_started_at = datetime.utcnow()
        try:
            client = resolve_client_for_company(db, company)
            result = ingest_from_client(
                db, company=company, client=client, since=company.last_polled_at
            )
            lifecycle_result = ingest_incoming_lifecycle_events(
                db, company=company, client=client, since=company.last_polled_at
            )
        except Exception as exc:
            # Une exception pendant `ingest_from_client` (ex. échec de flush SQL) laisse
            # la session dans un état "transaction rolled back" : sans ce rollback
            # explicite, la moindre requête suivante (y compris `company.id` ci-dessous,
            # dont l'attribut peut avoir été expiré) lève une `PendingRollbackError` qui
            # masquerait l'erreur d'origine et interromprait le polling des entreprises
            # suivantes — contrairement à l'intention du commentaire ci-dessous.
            db.rollback()
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

        company.last_polled_at = cycle_started_at
        db.commit()

        audit_trace_service.record_technical_log(
            db,
            log_type=LOG_TYPE,
            origin=LOG_ORIGIN,
            company_id=company.id,
            status="warning" if result.unrouted_invoice_ids else "success",
            new_count=len(result.created),
            updated_count=len(result.updated),
        )

        if lifecycle_result.created or lifecycle_result.unmatched_flow_ids or lifecycle_result.failed_flow_ids:
            details = None
            if lifecycle_result.unmatched_flow_ids or lifecycle_result.failed_flow_ids:
                details = (
                    f"non rattachés: {lifecycle_result.unmatched_flow_ids}; "
                    f"échecs: {lifecycle_result.failed_flow_ids}"
                )
            audit_trace_service.record_technical_log(
                db,
                log_type=LIFECYCLE_LOG_TYPE,
                origin=LOG_ORIGIN,
                company_id=company.id,
                status=(
                    "warning"
                    if (lifecycle_result.unmatched_flow_ids or lifecycle_result.failed_flow_ids)
                    else "success"
                ),
                new_count=len(lifecycle_result.created),
                details=details,
            )
