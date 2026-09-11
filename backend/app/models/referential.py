"""Référentiel, applications cibles et accès (spec.md § 6.1 / § 7.1.1)."""

import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, String, Table, Column, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RoutingMethod(str, enum.Enum):
    MAIL = "mail"
    AFNOR_API = "afnor_api"


class OAuthScope(str, enum.Enum):
    ROUTER_TO_SUPERPDP = "router_to_superpdp"
    CONSUMER_TO_ROUTER = "consumer_to_router"


class OAuthAppType(str, enum.Enum):
    CONFIDENTIAL = "confidential"
    PUBLIC = "public"


class Company(Base):
    """Entreprise gérée (spec.md § 6.1)."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    siren: Mapped[str] = mapped_column(String(9), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))


class PartnerDirectory(Base):
    """Annuaire des émetteurs/tiers connus du routeur (spec.md § 6.1)."""

    __tablename__ = "partner_directories"

    id: Mapped[int] = mapped_column(primary_key=True)
    siren: Mapped[str] = mapped_column(String(9), index=True)
    siret: Mapped[str | None] = mapped_column(String(14), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    routing_rules: Mapped[list["RoutingRule"]] = relationship(back_populates="partner")


class TargetApplication(Base):
    """Application cible (spec.md § 6.1 / § 4.9).

    Pour la méthode `afnor_api`, les paramètres décrits au § 4.9.2 (URLs de
    redirection, format de conversion préféré, type d'application, URL de webhook)
    sont portés par l'`OAuthApplication` liée (`oauth_application_id`) — c'est elle
    qui détient les identifiants OAuth réels (§ 4.10), pas `parameters`, pour éviter
    de dupliquer ces champs à deux endroits du modèle (redondance identifiée au lot 1,
    résolue au lot 4 en branchant l'authentification réelle)."""

    __tablename__ = "target_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    routing_method: Mapped[RoutingMethod] = mapped_column(String(20))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    oauth_application_id: Mapped[int | None] = mapped_column(
        ForeignKey("oauth_applications.id"), nullable=True
    )
    # Paramètres propres à la méthode mail (§ 4.9.1 : to/cc/bcc). Vide/non utilisé
    # pour la méthode afnor_api (cf. docstring ci-dessus).
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)

    company: Mapped[Company | None] = relationship()
    oauth_application: Mapped["OAuthApplication | None"] = relationship()
    routing_rules: Mapped[list["RoutingRule"]] = relationship(back_populates="target_application")


class RoutingRule(Base):
    """Classe d'association PartnerDirectory <-> TargetApplication (spec.md § 6.1)."""

    __tablename__ = "routing_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_directory_id: Mapped[int] = mapped_column(ForeignKey("partner_directories.id"))
    target_application_id: Mapped[int] = mapped_column(ForeignKey("target_applications.id"))
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    partner: Mapped[PartnerDirectory] = relationship(back_populates="routing_rules")
    target_application: Mapped[TargetApplication] = relationship(back_populates="routing_rules")


class OAuthApplication(Base):
    """Jeton d'accès par entreprise (spec.md § 6.1 / § 4.10) — deux usages distincts
    selon `scope` :

    - `consumer_to_router` (§ 4.9.2, lot 4) : identifiants que le routeur **émet**
      lui-même pour un consommateur (Odoo) — `client_secret_hash` suffit (hash
      irréversible, § 4.9.2), le secret en clair n'étant révélé qu'une fois à la
      création.
    - `router_to_superpdp` (§ 4.10, lot 6) : identifiants que **SuperPDP fournit** au
      routeur pour s'authentifier auprès d'elle — le secret doit être récupérable pour
      chaque rafraîchissement de jeton OAuth2, d'où `client_secret_encrypted` (chiffrement
      réversible, cf. `app.services.secrets_encryption`) plutôt qu'un hash. `token_cache`
      persiste le jeton/refresh token pyfrctc entre deux appels (§ 4.1/§ 4.8)."""

    __tablename__ = "oauth_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    client_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    client_secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_cache: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_type: Mapped[OAuthAppType] = mapped_column(String(20))
    scope: Mapped[OAuthScope] = mapped_column(String(30))
    redirect_urls: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    preferred_conversion_format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    afnor_api_version: Mapped[str | None] = mapped_column(String(10), nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    company: Mapped[Company] = relationship()


company_users = Table(
    "company_users",
    Base.metadata,
    Column("company_id", ForeignKey("companies.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)


class User(Base):
    """Utilisateur OIDC (spec.md § 6.1/NF3/NF4). `role` ("admin" voit toutes les
    entreprises, "user" est restreint à son périmètre) et `companies` (via
    `company_users`) forment ensemble l'"AccessScope" du § 6.1 — pas de table dédiée,
    ce couple suffit à représenter le périmètre de consultation d'un utilisateur."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="user")

    companies: Mapped[list[Company]] = relationship(secondary=company_users)
