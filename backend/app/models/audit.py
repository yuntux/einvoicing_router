"""Traçabilité (spec.md § 6.1, NF1) — branchée dès le lot 4 sur l'API AFNOR exposée à Odoo."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String
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
    http_status: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
