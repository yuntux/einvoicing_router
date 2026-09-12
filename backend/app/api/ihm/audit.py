"""Consultation des journaux de traçabilité (spec.md § 6.1) — écriture faite par
`app.services.audit_trace_service`, jamais exposée en modification depuis l'IHM."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.perimeter import apply_company_scope
from app.auth.session import get_current_user
from app.db.session import get_db
from app.models.audit import AuditLog, FlowTrace, TechnicalLog
from app.models.referential import User
from app.schemas.audit import AuditLogRead, FlowTraceRead, TechnicalLogRead

router = APIRouter()

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


@router.get("/flow-traces", response_model=list[FlowTraceRead])
def list_flow_traces(
    limit: int = Query(default=DEFAULT_LIMIT, le=MAX_LIMIT),
    db: Session = Depends(get_db),
):
    """Requêtes/réponses HTTP brutes de chaque appel API AFNOR (NF1) — pas de notion
    d'entreprise sur cette table (§ 6.1), donc pas de filtrage de périmètre ici."""
    return (
        db.query(FlowTrace)
        .order_by(FlowTrace.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/technical-logs", response_model=list[TechnicalLogRead])
def list_technical_logs(
    limit: int = Query(default=DEFAULT_LIMIT, le=MAX_LIMIT),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Résultat métier des traitements batch (ex. cycle de polling) — restreint au
    périmètre entreprises de l'utilisateur (§ NF4) comme les autres listes IHM."""
    query = apply_company_scope(
        db.query(TechnicalLog), user=user, company_id_column=TechnicalLog.company_id
    )
    return query.order_by(TechnicalLog.created_at.desc()).limit(limit).all()


@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(
    limit: int = Query(default=DEFAULT_LIMIT, le=MAX_LIMIT),
    db: Session = Depends(get_db),
):
    """Actions utilisateur sur l'IHM (NF9) — pas de notion d'entreprise sur cette
    table non plus, même limite que `FlowTrace`."""
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    user_ids = {row.user_id for row in rows if row.user_id is not None}
    emails = {}
    if user_ids:
        emails = {u.id: u.email for u in db.query(User).filter(User.id.in_(user_ids)).all()}
    return [
        AuditLogRead(
            id=row.id,
            user_id=row.user_id,
            user_email=emails.get(row.user_id) if row.user_id is not None else None,
            action=row.action,
            target=row.target,
            ip_address=row.ip_address,
            created_at=row.created_at,
        )
        for row in rows
    ]
