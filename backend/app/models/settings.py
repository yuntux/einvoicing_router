"""Configuration générale du routeur (spec.md § 6.1, § 4.7, § 4.9.1)."""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RouterSettings(Base):
    """Configuration générale, instance unique (id=1 par convention applicative).

    Porte le serveur d'envoi SMTP mutualisé pour toutes les applications cibles de
    type mail (§ 4.9.1) — le diagramme § 7.1.3 les regroupe sous `smtp_credentials`,
    éclaté ici en champs distincts (host/port/identifiants/expéditeur/TLS) pour rester
    directement utilisable par `smtplib` sans couche d'analyse supplémentaire."""

    __tablename__ = "router_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    technical_log_retention_days: Mapped[int] = mapped_column(Integer, default=15 * 365)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    smtp_from_address: Mapped[str | None] = mapped_column(String(255), nullable=True)


class BillingManagerContact(Base):
    """Adresse email d'un "Gestionnaire de facturation" (spec.md § 4.7) — destinataire
    des alertes de routage sans cible et d'échec définitif. Paramétré globalement,
    jamais par entreprise (les Gestionnaires de facturation ont une vue transverse)."""

    __tablename__ = "billing_manager_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
