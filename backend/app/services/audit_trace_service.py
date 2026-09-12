"""AuditTraceService — traçabilité NF1 (flux AFNOR) / NF9 (actions IHM) et journal
technique des traitements batch (spec.md § 6.1), avec trois granularités distinctes
(cf. docstring de `app.models.audit`)."""

from datetime import datetime

from fastapi import Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit import AuditLog, FlowTrace, TechnicalLog
from app.models.referential import User

# Marqueurs (sous-chaînes, insensibles à la casse) identifiant un en-tête HTTP sensible
# — la valeur est masquée avant stockage, jamais le nom de l'en-tête (utile au debug).
_SENSITIVE_HEADER_MARKERS = ("authorization", "cookie", "secret", "token", "key")
_REDACTED_VALUE = "***REDACTED***"


def redact_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
    """Masque la valeur des en-têtes sensibles (Authorization, cookies, secrets/tokens/
    clés) avant stockage en base — un `FlowTrace` ne doit jamais persister un jeton
    d'accès ou un secret client en clair (§ NF1)."""
    if headers is None:
        return None
    return {
        name: (
            _REDACTED_VALUE
            if any(marker in name.lower() for marker in _SENSITIVE_HEADER_MARKERS)
            else value
        )
        for name, value in headers.items()
    }


def record_flow_trace(
    db: Session,
    *,
    direction: str,
    afnor_api_version: str,
    request: dict,
    response: dict,
    http_status: int,
    correlation_id: str | None = None,
    request_headers: dict[str, str] | None = None,
    response_headers: dict[str, str] | None = None,
) -> FlowTrace:
    trace = FlowTrace(
        direction=direction,
        afnor_api_version=afnor_api_version,
        request=request,
        response=response,
        request_headers=redact_headers(request_headers),
        response_headers=redact_headers(response_headers),
        http_status=http_status,
        **({"correlation_id": correlation_id} if correlation_id else {}),
    )
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return trace


def record_odoo_flow_trace(
    db: Session,
    request: Request,
    *,
    afnor_api_version: str,
    endpoint: str,
    response: dict,
    http_status: int,
    correlation_id: str | None = None,
    **extra_request_fields,
) -> FlowTrace:
    """Trace un échange Odoo -> routeur (§ 4.4/NF1) : direction et en-têtes de requête
    sont toujours les mêmes pour ce sens, seul le contenu métier de `request` varie
    d'un endpoint à l'autre — passé via `extra_request_fields` (ex. `siren=...`)."""
    return record_flow_trace(
        db,
        direction="odoo_to_router",
        afnor_api_version=afnor_api_version,
        request={"endpoint": endpoint, **extra_request_fields},
        response=response,
        http_status=http_status,
        correlation_id=correlation_id,
        request_headers=dict(request.headers),
    )


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


def record_user_action(
    db: Session,
    request: Request,
    user: User | None,
    *,
    action: str,
    target: str,
) -> AuditLog:
    """Variante de `record_audit_log` qui déduit `user_id`/`ip_address` de la requête
    IHM courante — évite de répéter `user.id if user else None` /
    `request.client.host if request.client else None` à chaque endpoint (§ NF9)."""
    return record_audit_log(
        db,
        action=action,
        target=target,
        user_id=user.id if user else None,
        ip_address=request.client.host if request.client else None,
    )


def get_last_logins(db: Session, user_ids: list[int]) -> dict[int, datetime]:
    """Date/heure de dernière connexion par utilisateur, dérivée du journal d'audit
    (action `"login"`, cf. `app.api.ihm.auth`) plutôt que dupliquée dans une colonne
    dédiée sur `User` — l'audit log est déjà la source de vérité de cet événement."""
    if not user_ids:
        return {}
    rows = (
        db.query(AuditLog.user_id, func.max(AuditLog.created_at))
        .filter(AuditLog.action == "login", AuditLog.user_id.in_(user_ids))
        .group_by(AuditLog.user_id)
        .all()
    )
    return {user_id: last_login for user_id, last_login in rows}


def get_last_login(db: Session, user_id: int) -> datetime | None:
    """Variante mono-utilisateur de `get_last_logins` (utilisée pour la colonne
    "dernière connexion" de la page Gestion des accès — l'admin y consulte la
    connexion la plus récente de chaque utilisateur, y compris "maintenant" s'il
    vient de se connecter)."""
    return get_last_logins(db, [user_id]).get(user_id)


def get_previous_login(db: Session, user_id: int) -> datetime | None:
    """Avant-dernière connexion de l'utilisateur (`None` s'il ne s'est jamais connecté
    qu'une seule fois, ou jamais) — utilisée pour l'affichage "Dernière connexion"
    dans le pied de la sidebar (`/auth/me`) : y montrer la connexion en cours (donc
    "maintenant") serait sans intérêt ; montrer la *précédente* permet à
    l'utilisateur de repérer une connexion suspecte (ex. un jour où il n'a pas
    travaillé)."""
    rows = (
        db.query(AuditLog.created_at)
        .filter(AuditLog.action == "login", AuditLog.user_id == user_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(1)
        .limit(1)
        .all()
    )
    return rows[0][0] if rows else None
