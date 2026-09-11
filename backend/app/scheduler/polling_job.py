"""Job de polling périodique (spec.md § 4.1, lot 6) — déclencheur découplé introduit
au lot 2 (`InvoiceIngestionService.ingest_from_client`), enfin branché sur le
scheduler définitif plutôt qu'appelé uniquement via `/invoices/simulate` (dev/tests)."""

from sqlalchemy.orm import Session

from app.models.referential import Company
from app.services.client_factory import resolve_client_for_company
from app.services.invoice_ingestion_service import ingest_from_client


def run_polling_cycle(db: Session) -> None:
    for company in db.query(Company).order_by(Company.id).all():
        client = resolve_client_for_company(db, company)
        try:
            ingest_from_client(db, company=company, client=client)
        except Exception:
            # Une entreprise mal configurée (pas d'identifiants SuperPDP, § 4.10) ne
            # doit pas empêcher le polling des autres entreprises gérées.
            continue
