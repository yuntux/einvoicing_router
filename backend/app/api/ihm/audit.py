"""Consultation des journaux de traçabilité (spec.md § 6.1) — écriture faite par
`app.services.audit_trace_service`, jamais exposée en modification depuis l'IHM."""

from datetime import date, datetime, timedelta

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


def _created_at_bounds(column, created_from: date | None, created_to: date | None):
    """Filtres `>= created_from` / `< created_to + 1 jour` sur une colonne DATETIME à
    partir de bornes DATE (§ 8.3, même logique que les filtres de dates de la page
    Factures) — la borne de fin doit inclure toute la journée, pas seulement minuit."""
    filters = []
    if created_from is not None:
        filters.append(column >= datetime.combine(created_from, datetime.min.time()))
    if created_to is not None:
        filters.append(column < datetime.combine(created_to, datetime.min.time()) + timedelta(days=1))
    return filters


@router.get("/flow-traces", response_model=list[FlowTraceRead])
def list_flow_traces(
    limit: int = Query(default=DEFAULT_LIMIT, le=MAX_LIMIT),
    created_from: date | None = None,
    created_to: date | None = None,
    direction: str | None = None,
    afnor_api_version: str | None = None,
    http_status: int | None = None,
    correlation_id: str | None = None,
    db: Session = Depends(get_db),
):
    """Requêtes/réponses HTTP brutes de chaque appel API AFNOR (NF1) — pas de notion
    d'entreprise sur cette table (§ 6.1), donc pas de filtrage de périmètre ici."""
    query = db.query(FlowTrace)
    for condition in _created_at_bounds(FlowTrace.created_at, created_from, created_to):
        query = query.filter(condition)
    if direction is not None:
        query = query.filter(FlowTrace.direction == direction)
    if afnor_api_version is not None:
        query = query.filter(FlowTrace.afnor_api_version == afnor_api_version)
    if http_status is not None:
        query = query.filter(FlowTrace.http_status == http_status)
    if correlation_id is not None:
        query = query.filter(FlowTrace.correlation_id.contains(correlation_id))
    return query.order_by(FlowTrace.created_at.desc()).limit(limit).all()


@router.get("/technical-logs", response_model=list[TechnicalLogRead])
def list_technical_logs(
    limit: int = Query(default=DEFAULT_LIMIT, le=MAX_LIMIT),
    created_from: date | None = None,
    created_to: date | None = None,
    log_type: str | None = None,
    origin: str | None = None,
    company_id: int | None = None,
    status: str | None = None,
    new_count: int | None = None,
    updated_count: int | None = None,
    details: str | None = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Résultat métier des traitements batch (ex. cycle de polling) — restreint au
    périmètre entreprises de l'utilisateur (§ NF4) comme les autres listes IHM."""
    query = apply_company_scope(
        db.query(TechnicalLog), user=user, company_id_column=TechnicalLog.company_id
    )
    for condition in _created_at_bounds(TechnicalLog.created_at, created_from, created_to):
        query = query.filter(condition)
    if log_type is not None:
        query = query.filter(TechnicalLog.log_type == log_type)
    if origin is not None:
        query = query.filter(TechnicalLog.origin == origin)
    if company_id is not None:
        query = query.filter(TechnicalLog.company_id == company_id)
    if status is not None:
        query = query.filter(TechnicalLog.status == status)
    if new_count is not None:
        query = query.filter(TechnicalLog.new_count == new_count)
    if updated_count is not None:
        query = query.filter(TechnicalLog.updated_count == updated_count)
    if details is not None:
        query = query.filter(TechnicalLog.details.contains(details))
    return query.order_by(TechnicalLog.created_at.desc()).limit(limit).all()


@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(
    limit: int = Query(default=DEFAULT_LIMIT, le=MAX_LIMIT),
    created_from: date | None = None,
    created_to: date | None = None,
    user_email: str | None = None,
    action: str | None = None,
    target: str | None = None,
    ip_address: str | None = None,
    db: Session = Depends(get_db),
):
    """Actions utilisateur sur l'IHM (NF9) — pas de notion d'entreprise sur cette
    table non plus, même limite que `FlowTrace`."""
    query = db.query(AuditLog)
    for condition in _created_at_bounds(AuditLog.created_at, created_from, created_to):
        query = query.filter(condition)
    if user_email is not None:
        query = query.filter(
            AuditLog.user_id.in_(
                db.query(User.id).filter(User.email.ilike(f"%{user_email}%"))
            )
        )
    if action is not None:
        query = query.filter(AuditLog.action.contains(action))
    if target is not None:
        query = query.filter(AuditLog.target.contains(target))
    if ip_address is not None:
        query = query.filter(AuditLog.ip_address.contains(ip_address))
    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

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
