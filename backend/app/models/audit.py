"""Traçabilité (spec.md § 6.1, NF1/NF9) — `FlowTrace` branchée dès le lot 4 sur l'API
AFNOR exposée à Odoo ; `TechnicalLog`/`AuditLog` complètent la traçabilité au lot 8 :
trois journaux à la portée distincte (§ 6.1) — `FlowTrace` trace les requêtes/réponses
HTTP brutes d'un flux AFNOR, `TechnicalLog` le résultat métier d'un traitement batch
(ex. cycle de polling), `AuditLog` les actions d'un utilisateur sur l'IHM."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FlowTrace(Base):
    """Traçabilité NF1 : requête/réponse brute de chaque appel API AFNOR, avec un
    correlationID commun pour reconstituer un flux de bout en bout."""

    __tablename__ = "flow_traces"

    id: Mapped[int] = mapped_column(primary_key=True)
    correlation_id: Mapped[str] = mapped_column(
        String(36), default=lambda: str(uuid.uuid4()), index=True
    )
    direction: Mapped[str] = mapped_column(String(30))
    afnor_api_version: Mapped[str] = mapped_column(String(10))
    request: Mapped[dict] = mapped_column(JSON)
    response: Mapped[dict] = mapped_column(JSON)
    # En-têtes HTTP bruts, quand disponibles (`None` sinon — ex. en-têtes de réponse
    # renvoyée à Odoo, non accessibles au moment de l'enregistrement de la trace).
    # Les valeurs sensibles (Authorization, cookies, secrets/tokens/clés) sont
    # masquées avant stockage par `audit_trace_service.redact_headers`.
    request_headers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_headers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    http_status: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TechnicalLog(Base):
    """Journal technique du résultat métier d'un traitement batch (§ 6.1) — ex. un
    cycle de polling SuperPDP (§ 4.1) : combien de factures nouvelles/mises à jour,
    succès/avertissement/échec. Complémentaire de `FlowTrace` (requêtes HTTP brutes).
    Purgé selon `RouterSettings.technical_log_retention_days` (15 ans par défaut)."""

    __tablename__ = "technical_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    log_type: Mapped[str] = mapped_column(String(50))
    origin: Mapped[str] = mapped_column(String(100))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AuditLog(Base):
    """Audit applicatif des actions utilisateur sur l'IHM (NF9), distinct du traçage
    des flux (NF1/`FlowTrace`). `user_id` reste nullable : hors authentification
    (`settings.oidc_mode == "disabled"`, § NF3), aucun utilisateur n'est identifiable."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50))
    target: Mapped[str] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
