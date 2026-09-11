"""AuditTraceService — traçabilité NF1 (flux AFNOR) / NF9 (actions IHM) et journal
technique des traitements batch (spec.md § 6.1), avec trois granularités distinctes
(cf. docstring de `app.models.audit`)."""

from sqlalchemy.orm import Session

from app.models.audit import AuditLog, FlowTrace, TechnicalLog


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


def record_technical_log(
    db: Session,
    *,
    log_type: str,
    origin: str,
    status: str,
    company_id: int | None = None,
    new_count: int = 0,
    updated_count: int = 0,
    details: str | None = None,
) -> TechnicalLog:
    """Résultat métier d'un traitement batch (§ 6.1) — ex. un cycle de polling."""
    log = TechnicalLog(
        log_type=log_type,
        origin=origin,
        company_id=company_id,
        status=status,
        new_count=new_count,
        updated_count=updated_count,
        details=details,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def record_audit_log(
    db: Session,
    *,
    action: str,
    target: str,
    user_id: int | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Action d'un utilisateur sur l'IHM (NF9) — ex. téléchargement d'une facture."""
    log = AuditLog(user_id=user_id, action=action, target=target, ip_address=ip_address)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
