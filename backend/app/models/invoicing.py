"""Facture, routage effectif (spec.md § 6.1 / § 7.1.2) — hors cycle de vie (§ 6.2, lot 3)."""

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.referential import Company, PartnerDirectory, TargetApplication


class InvoiceType(str, enum.Enum):
    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"


class TransferStatus(str, enum.Enum):
    TO_SEND = "to_send"
    SENT = "sent"
    FAILED = "failed"
    RETRYING = "retrying"
    FAILED_FINAL = "failed_final"


class Invoice(Base):
    """Facture reçue (spec.md § 6.1) — les factures émises ne sont pas indexées ici."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("company_id", "certified_platform_flow_id", name="uq_invoice_company_flow"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    partner_directory_id: Mapped[int | None] = mapped_column(
        ForeignKey("partner_directories.id"), nullable=True
    )

    emitter_siren: Mapped[str] = mapped_column(String(9), index=True)
    emitter_siret: Mapped[str | None] = mapped_column(String(14), nullable=True)

    invoice_number: Mapped[str] = mapped_column(String(100), index=True)
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    invoice_type: Mapped[InvoiceType] = mapped_column(String(20), default=InvoiceType.INVOICE)

    lifecycle_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1000))

    certified_platform_flow_id: Mapped[str] = mapped_column(String(100), index=True)
    certified_platform_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    certified_platform_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    amount_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_excl_tax: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    syntax: Mapped[str | None] = mapped_column(String(30), nullable=True)
    processing_rule: Mapped[str | None] = mapped_column(String(30), nullable=True)

    afnor_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    afnor_api_version: Mapped[str | None] = mapped_column(String(10), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Enveloppe de transport du flux AFNOR d'origine (schéma officiel "AFNOR Flow
    # Service" — objet Flow), distincte des champs métier de la facture ci-dessus
    # (cf. app/afnor/invoice_parsing.py sur la distinction transport/métier).
    flow_profile: Mapped[str | None] = mapped_column(String(30), nullable=True)
    processing_rule_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tracking_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    flow_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    flow_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    flow_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ack_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ack_details: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # § 4.7 : garde-fou anti-spam — l'alerte "facture non routée" ne doit partir qu'une
    # fois par facture, jamais rejouée à chaque cycle de polling tant qu'elle reste
    # sans cible (cf. app.services.invoice_ingestion_service._route_invoice).
    unrouted_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    company: Mapped[Company] = relationship()
    partner: Mapped[PartnerDirectory | None] = relationship()
    routings: Mapped[list["InvoiceRouting"]] = relationship(back_populates="invoice")


class InvoiceRouting(Base):
    """Table de routage effective par facture/cible (spec.md § 6.1 / § 4.7)."""

    __tablename__ = "invoice_routings"
    __table_args__ = (
        UniqueConstraint("invoice_id", "target_application_id", name="uq_routing_invoice_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    target_application_id: Mapped[int] = mapped_column(ForeignKey("target_applications.id"))
    transfer_status: Mapped[TransferStatus] = mapped_column(
        String(20), default=TransferStatus.TO_SEND
    )
    attempt_count: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    invoice: Mapped[Invoice] = relationship(back_populates="routings")
    target_application: Mapped[TargetApplication] = relationship()
