"""Référentiel, applications cibles et accès (spec.md § 6.1 / § 7.1.1)."""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    String,
    Table,
    Column,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import AuditColumnsMixin


class RoutingMethod(str, enum.Enum):
    MAIL = "mail"
    AFNOR_API = "afnor_api"


class OAuthAppType(str, enum.Enum):
    CONFIDENTIAL = "confidential"
    PUBLIC = "public"


class Company(AuditColumnsMixin, Base):
    """Entreprise gérée (spec.md § 6.1)."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    siren: Mapped[str] = mapped_column(String(9), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    # Curseur du polling incrémental (§ 4.1) : horodatage du début du dernier cycle de
    # polling réussi pour cette entreprise, transmis comme `since` au client AFNOR pour
    # ne re-scanner que les flux mis à jour depuis — sans lui, chaque cycle rescannait
    # tout l'historique (depuis l'an 2000) à chaque déclenchement, § lot 9.
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Identifiants OAuth2 que la plateforme certifiée (SuperPDP) fournit AU ROUTEUR
    # pour s'authentifier auprès d'elle (§ 4.10, scope "router_to_superpdp") — un seul
    # jeu par entreprise gérée, porté directement ici plutôt que par une table
    # `oauth_applications` à part : le modèle précédent (une table unique gérant deux
    # scopes aux colonnes disjointes selon le scope) était source de confusion, ces
    # identifiants sont en réalité un attribut de l'entreprise elle-même, pas une
    # entité indépendante. Secret chiffré (réversible, cf.
    # `app.services.secrets_encryption`) car nécessaire en clair à chaque
    # rafraîchissement de jeton OAuth2 pyfrctc (contrairement au secret émis par le
    # routeur à ses propres consommateurs, cf. `TargetApplication.parameters`, qui lui
    # reste un hash irréversible).
    certified_platform_client_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    certified_platform_client_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Jeton/refresh token pyfrctc en cache entre deux appels (§ 4.1/§ 4.8).
    certified_platform_token_cache: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plateforme AFNOR certifiée à utiliser pour cette entreprise — une clé du dict
    # `pyfrctc.pyfrctc.PLATFORMS` (§ 4.10, ex. "superpdp"). `None` = plateforme par
    # défaut du serveur (`settings.certified_platform`) : permet de pointer une
    # entreprise vers un environnement AFNOR distinct sans redéployer le routeur.
    certified_platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Identifiant de cette entreprise tel qu'enregistré dans l'annuaire de la
    # plateforme certifiée (§ 4.10) — distinct du SIREN légal (`siren`, validé par sa
    # clé de Luhn) : un bac à sable AFNOR peut immatriculer ses entités fictives sous
    # des identifiants techniques qui ne sont pas des SIREN valides (ex. "000000001").
    # Utilisé à la place de `siren` dans les échanges avec l'annuaire/CDAR
    # (`cdar_service.build_data_dict`) quand renseigné ; `None` = utiliser `siren`.
    certified_platform_directory_id: Mapped[str | None] = mapped_column(String(35), nullable=True)


class PartnerDirectory(AuditColumnsMixin, Base):
    """Annuaire des émetteurs/tiers connus du routeur (spec.md § 6.1)."""

    __tablename__ = "partner_directories"

    id: Mapped[int] = mapped_column(primary_key=True)
    siren: Mapped[str] = mapped_column(String(9), index=True)
    siret: Mapped[str | None] = mapped_column(String(14), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    routing_rules: Mapped[list["RoutingRule"]] = relationship(back_populates="partner")


class TargetApplication(AuditColumnsMixin, Base):
    """Application cible (spec.md § 6.1 / § 4.9).

    `parameters` (JSON) porte les paramètres propres à la méthode de routage choisie,
    quelle qu'elle soit — `from`/`to`/`cc`/`bcc` pour `mail` (§ 4.9.1 ; `from`
    facultatif, surcharge par application cible de l'adresse d'expédition globale
    `RouterSettings.smtp_from_address` sinon utilisée par défaut), et pour `afnor_api`
    (§ 4.9.2/§ 4.10) : `client_id`, `client_secret_hash` (hash irréversible, le secret
    en clair n'étant révélé qu'une fois à la création), `app_type`, `redirect_urls`,
    `preferred_conversion_format`, `webhook_url`. Une seule colonne pour les deux
    méthodes plutôt qu'une table `oauth_applications` séparée : ces champs ne sont
    jamais qu'une variante des "paramètres de la méthode de routage", pas une entité
    indépendante — les propriétés ci-dessous (`client_id`, `webhook_url`...) exposent
    un accès typé pratique à ces clés pour le reste du code, sans dupliquer le
    stockage. Client_id/secret sont générés par le routeur lui-même (jamais fournis
    par l'appelant), analogue au comportement du formulaire d'enregistrement
    d'application de SuperPDP.

    `company_id` est obligatoire quelle que soit `routing_method` (y compris `mail`) :
    une application cible sans entreprise rattachée ne peut pas être distinguée par
    `RoutingRuleService.resolve` selon l'entreprise réceptrice, ce qui fait fuiter le
    routage d'un même fournisseur facturant plusieurs entreprises gérées vers toutes
    leurs applications mail au lieu de la seule concernée (§ NF2 : cloisonnement
    strict, aligné sur ce qui était déjà appliqué à `afnor_api`)."""

    __tablename__ = "target_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    routing_method: Mapped[RoutingMethod] = mapped_column(String(20))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    # Désactivation sans suppression (conserve l'historique de routage, § 6.1) : une
    # application inactive n'est plus jamais retenue par RoutingRuleService.resolve
    # pour de nouvelles factures, mais les InvoiceRouting déjà créés restent inchangés.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    company: Mapped[Company] = relationship()
    routing_rules: Mapped[list["RoutingRule"]] = relationship(back_populates="target_application")

    # Accès typé aux clés de `parameters` utilisées par la méthode `afnor_api`
    # (§ 4.9.2/§ 4.10) — `None` pour une application `mail`, ou une clé absente.
    @property
    def client_id(self) -> str | None:
        return self.parameters.get("client_id") if self.routing_method == RoutingMethod.AFNOR_API else None

    @property
    def client_secret_hash(self) -> str | None:
        return (
            self.parameters.get("client_secret_hash")
            if self.routing_method == RoutingMethod.AFNOR_API
            else None
        )

    @property
    def app_type(self) -> str | None:
        return self.parameters.get("app_type") if self.routing_method == RoutingMethod.AFNOR_API else None

    @property
    def redirect_urls(self) -> str | None:
        return (
            self.parameters.get("redirect_urls")
            if self.routing_method == RoutingMethod.AFNOR_API
            else None
        )

    @property
    def preferred_conversion_format(self) -> str | None:
        return (
            self.parameters.get("preferred_conversion_format")
            if self.routing_method == RoutingMethod.AFNOR_API
            else None
        )

    @property
    def webhook_url(self) -> str | None:
        return self.parameters.get("webhook_url") if self.routing_method == RoutingMethod.AFNOR_API else None

    # Accès typé aux clés de `parameters` utilisées par la méthode `mail` (§ 4.9.1) —
    # `None`/liste vide pour une application `afnor_api`, ou une clé absente.
    @property
    def from_address(self) -> str | None:
        return self.parameters.get("from") if self.routing_method == RoutingMethod.MAIL else None

    @property
    def to(self) -> list[str]:
        return list(self.parameters.get("to") or []) if self.routing_method == RoutingMethod.MAIL else []

    @property
    def cc(self) -> list[str]:
        return list(self.parameters.get("cc") or []) if self.routing_method == RoutingMethod.MAIL else []

    @property
    def bcc(self) -> list[str]:
        return list(self.parameters.get("bcc") or []) if self.routing_method == RoutingMethod.MAIL else []


class RoutingRule(AuditColumnsMixin, Base):
    """Classe d'association PartnerDirectory <-> TargetApplication (spec.md § 6.1).

    Pas de période de validité ni de drapeau `active` séparé : l'existence même de la
    ligne signifie que le routage est actif pour ce couple (fournisseur, application
    cible) — cocher/décocher la case dans la matrice IHM crée ou supprime directement
    la ligne (§ 4.3)."""

    __tablename__ = "routing_rules"
    __table_args__ = (
        UniqueConstraint(
            "partner_directory_id", "target_application_id", name="uq_routing_rule_partner_target"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_directory_id: Mapped[int] = mapped_column(ForeignKey("partner_directories.id"))
    target_application_id: Mapped[int] = mapped_column(ForeignKey("target_applications.id"))

    partner: Mapped[PartnerDirectory] = relationship(back_populates="routing_rules")
    target_application: Mapped[TargetApplication] = relationship(back_populates="routing_rules")


company_users = Table(
    "company_users",
    Base.metadata,
    Column("company_id", ForeignKey("companies.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)


class User(AuditColumnsMixin, Base):
    """Utilisateur OIDC (spec.md § 6.1/NF3/NF4). `role` ("admin" voit toutes les
    entreprises, "user" est restreint à son périmètre) et `companies` (via
    `company_users`) forment ensemble l'"AccessScope" du § 6.1 — pas de table dédiée,
    ce couple suffit à représenter le périmètre de consultation d'un utilisateur.

    Un compte est **pré-provisionné** par un administrateur depuis l'IHM (email seul,
    `oidc_subject` nul, `name` nul) avant la première connexion de son titulaire — cf.
    `app.services.user_service.resolve_login_user`, qui rattache `oidc_subject` à la
    ligne existante lors de cette première connexion plutôt que d'en créer une
    nouvelle. `is_active` permet de révoquer un accès sans supprimer l'historique
    (audit, factures consultées) attaché à l'utilisateur."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    companies: Mapped[list[Company]] = relationship(secondary=company_users)
