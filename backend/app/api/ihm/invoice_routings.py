from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.invoicing import InvoiceRouting, TransferStatus
from app.schemas.invoice_routing import (
    FailedInvoiceRoutingRead,
    ReplayRoutingResult,
    ReplayRoutingsRequest,
)
from app.services import retry_scheduler_service

router = APIRouter()

# États affichés dans la liste des échecs (§ 4.7) : en cours de retry automatique ou
# en échec définitif — rejeu manuel possible dans les deux cas.
FAILURE_STATUSES = (TransferStatus.RETRYING, TransferStatus.FAILED_FINAL)


@router.get("/failed", response_model=list[FailedInvoiceRoutingRead])
def list_failed_routings(db: Session = Depends(get_db)):
    rows = (
        db.query(InvoiceRouting)
        .filter(InvoiceRouting.transfer_status.in_(FAILURE_STATUSES))
        .order_by(InvoiceRouting.id)
        .all()
    )
    return [
        FailedInvoiceRoutingRead(
            id=row.id,
            invoice_id=row.invoice_id,
            invoice_number=row.invoice.invoice_number,
            emitter_siren=row.invoice.emitter_siren,
            target_application_id=row.target_application_id,
            target_application_name=row.target_application.name,
            transfer_status=row.transfer_status,
            attempt_count=row.attempt_count,
            next_attempt_at=row.next_attempt_at,
        )
        for row in rows
    ]


@router.post("/replay", response_model=list[ReplayRoutingResult])
def replay_routings(payload: ReplayRoutingsRequest, db: Session = Depends(get_db)):
    results = []
    for routing_id in payload.routing_ids:
        routing = db.get(InvoiceRouting, routing_id)
        if routing is None:
            raise HTTPException(status_code=404, detail=f"InvoiceRouting {routing_id} not found")
        success = retry_scheduler_service.replay_manual(db, routing=routing)
        results.append(ReplayRoutingResult(routing_id=routing_id, success=success))
    return results


@router.post("/run-send-cycle", status_code=204)
def run_send_cycle(db: Session = Depends(get_db)):
    """Force immédiatement un passage du cycle d'envoi/retry (§ 4.7), sans attendre le
    prochain déclenchement du scheduler (toutes les `retry_interval_minutes`)."""
    retry_scheduler_service.run_send_cycle(db)
