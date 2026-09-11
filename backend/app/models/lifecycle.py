"""Cycle de vie de la facture — inspiré de `l10n_fr_einvoicing` (spec.md § 6.2 / § 7.1.2)."""

import enum
from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, JSON, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.invoicing import Invoice
from app.models.referential import Company


class EventDirection(str, enum.Enum):
    IN = "in"
    OUT = "out"


class AfnorFlowState(str, enum.Enum):
    CREATED = "created"
    GENERATED = "generated"
    SENT = "sent"
    DOWNLOADED = "downloaded"
    DONE = "done"
    ERROR = "error"
    CANCEL = "cancel"


class AfnorFlowType(str, enum.Enum):
    CUSTOMER_INVOICE_LC = "CustomerInvoiceLC"
    SUPPLIER_INVOICE_LC = "SupplierInvoiceLC"


class AfnorFlow(Base):
    """Flux AFNOR XP Z12-013 générique (spec.md § 6.2) — cycle de vie technique
    distinct du cycle de vie métier de la facture. Aucune génération CDAR réelle au
    lot 3 : `state` reste à `created` tant que le lot 6 (pyfrctc) n'est pas branché."""

    __tablename__ = "afnor_flows"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    flow_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    direction: Mapped[EventDirection] = mapped_column(String(10))
    flow_type: Mapped[AfnorFlowType] = mapped_column(String(30))
    syntax: Mapped[str] = mapped_column(String(20), default="CDAR")
    processing_rule: Mapped[str | None] = mapped_column(String(30), nullable=True)
    state: Mapped[AfnorFlowState] = mapped_column(String(20), default=AfnorFlowState.CREATED)
    file_bin: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    data_dict: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    invoice: Mapped[Invoice] = relationship()


class LifecycleEvent(Base):
    """Message de cycle de vie (spec.md § 6.2, ≈ `fr.einvoicing.event`)."""

    __tablename__ = "lifecycle_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    event_datetime: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(30))
    direction: Mapped[EventDirection] = mapped_column(String(10))
    afnor_flow_id: Mapped[int | None] = mapped_column(ForeignKey("afnor_flows.id"), nullable=True)
    amount: Mapped[float | None] = mapped_column(nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    invoice: Mapped[Invoice] = relationship()
    company: Mapped[Company] = relationship()
    afnor_flow: Mapped[AfnorFlow | None] = relationship()
    details: Mapped[list["LifecycleEventDetail"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    payments: Mapped[list["LifecycleEventPayment"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["LifecycleEventAttachment"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class LifecycleEventDetail(Base):
    """Motif/action/commentaire (spec.md § 6.2, ≈ `fr.einvoicing.event.detail`)."""

    __tablename__ = "lifecycle_event_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("lifecycle_events.id"))
    reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    action: Mapped[str | None] = mapped_column(String(10), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    event: Mapped[LifecycleEvent] = relationship(back_populates="details")


class LifecycleEventPayment(Base):
    """Ligne de paiement (spec.md § 6.2, ≈ `fr.einvoicing.event.payment`) — statut
    `payment_sent`, reçu uniquement (§ 4.2), jamais créée par saisie manuelle."""

    __tablename__ = "lifecycle_event_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("lifecycle_events.id"))
    amount: Mapped[float] = mapped_column()
    currency: Mapped[str] = mapped_column(String(3))
    payment_date: Mapped[date] = mapped_column()

    event: Mapped[LifecycleEvent] = relationship(back_populates="payments")


class LifecycleEventAttachment(Base):
    """Pièce jointe associée à un événement (spec.md § 6.2)."""

    __tablename__ = "lifecycle_event_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("lifecycle_events.id"))
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    event: Mapped[LifecycleEvent] = relationship(back_populates="attachments")
