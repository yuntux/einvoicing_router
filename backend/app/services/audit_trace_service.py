"""AuditTraceService — enregistrement de la traçabilité NF1 (spec.md § 6.1)."""

from sqlalchemy.orm import Session

from app.models.audit import FlowTrace


def record_flow_trace(
    db: Session,
    *,
    direction: str,
    afnor_api_version: str,
    request: dict,
    response: dict,
    http_status: int,
    correlation_id: str | None = None,
) -> FlowTrace:
    trace = FlowTrace(
        direction=direction,
        afnor_api_version=afnor_api_version,
        request=request,
        response=response,
        http_status=http_status,
        **({"correlation_id": correlation_id} if correlation_id else {}),
    )
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return trace
