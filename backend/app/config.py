from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ROUTER_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./router.db"
    invoice_storage_root: str = "./data/invoices"

    # Signature des jetons d'accès émis pour l'API AFNOR exposée aux consommateurs
    # (§ 4.4/§ 4.10, applications OAuth Odoo). À surcharger via ROUTER_JWT_SECRET en
    # dehors du développement local.
    jwt_secret: str = "dev-insecure-secret-change-me"
    jwt_expiry_seconds: int = 3600

    # Signature des jetons de session IHM (utilisateur humain, § NF3) — volontairement
    # distincte de `jwt_secret` : un jeton de session ne doit jamais pouvoir être
    # rejoué comme jeton d'application OAuth (ou inversement), même si l'un des deux
    # secrets venait à fuiter. Sert aussi de clé au `SessionMiddleware` Starlette qui
    # transporte l'état OIDC (§ NF3, app/main.py) — même périmètre de confiance
    # (session du navigateur IHM). À surcharger via ROUTER_SESSION_SECRET en
    # dehors du développement local.
    session_secret: str = "dev-insecure-session-secret-change-me"

    # Scheduler définitif (§ 4.7) : cycle de rejeu automatique des envois en échec.
    # Désactivé dans les tests (cf. conftest.py) pour ne pas démarrer de thread de fond
    # contre la base réelle pendant l'exécution de la suite.
    scheduler_enabled: bool = True
    retry_interval_minutes: int = 30

    # Client AFNOR côté plateforme certifiée (SuperPDP, § 4.1/§ 4.8, lot 6) : "fake"
    # (fixtures, défaut dev/tests) ou "pyfrctc" (client réel, nécessite des
    # identifiants de plateforme certifiée par entreprise).
    certified_platform_client_mode: str = "fake"
    certified_platform: str = "superpdp"
    # Serveur Saxon pour la validation schématron des CDAR (optionnel, § 4.2/NF7) —
    # sans lui, seule la validation XSD (locale, sans réseau) est effectuée.
    saxon_server_url: str | None = None
    polling_interval_minutes: int = 15
    webhook_timeout_seconds: int = 10

    # Clé de chiffrement symétrique des secrets client de plateforme certifiée par
    # entreprise (`Company.certified_platform_client_secret_encrypted`, § 4.10) —
    # toujours distincte de `jwt_secret`/`session_secret`, sans repli automatique sur
    # l'un ou l'autre : la fuite d'un secret de signature JWT ne doit jamais suffire à
    # déchiffrer les identifiants de plateforme certifiée de toutes les entreprises
    # gérées. À surcharger via ROUTER_SECRETS_ENCRYPTION_KEY en dehors du
    # développement local.
    secrets_encryption_key: str = "dev-insecure-encryption-key-change-me"

    # Authentification IHM (NF3, lot 7) : "disabled" (aucune authentification requise
    # — dev/tests uniquement, jamais en production), "dev" (connexion locale sans IdP
    # réel, pour exercer le périmètre d'accès en développement) ou "entra_id" (flux
    # OIDC réel contre le tenant Microsoft Entra ID configuré).
    #
    # Volontairement SANS valeur par défaut : tant que `require_current_user`/
    # `require_admin` (app/auth/session.py) ne bloquent jamais rien en mode
    # "disabled", un déploiement qui oublierait de positionner cette variable ne doit
    # jamais se retrouver à exposer tout l'IHM sans authentification par un simple
    # défaut silencieux — ROUTER_OIDC_MODE doit être positionnée explicitement dans
    # tous les environnements (dev, CI, migrations, production), cf. README.
    oidc_mode: str
    oidc_tenant_id: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str = "http://localhost:8000/api/ihm/auth/callback"
    # URL vers laquelle rediriger le navigateur une fois la session IHM établie.
    frontend_base_url: str = "http://localhost:5173"
    session_cookie_name: str = "router_session"
    session_expiry_seconds: int = 8 * 3600

    # Allowlist IPv4/IPv6 (NF6, lot 7) : désactivée dans les tests (cf. conftest.py)
    # pour ne pas faire dépendre chaque requête HTTP d'un accès à la base réelle
    # (`SessionLocal`, hors du mécanisme de substitution `get_db` propre à FastAPI).
    ip_allowlist_enabled: bool = True

    # Limitation de débit (NF6) sur `POST /oauth/token` et `GET /auth/login` — filet
    # de sécurité défense-en-profondeur contre le brute-force/DoS applicatif, désactivé
    # dans les tests (cf. conftest.py) qui appellent ces endpoints bien plus souvent
    # qu'un usage réel. En mémoire, par IP cliente (cf. app/auth/rate_limit.py).
    rate_limit_enabled: bool = True
    rate_limit_max_requests: int = 20
    rate_limit_window_seconds: int = 60

    # Purge de TechnicalLog (§ 6.1, lot 8) : cycle quotidien, durée de rétention pilotée
    # par RouterSettings.technical_log_retention_days (15 ans par défaut).
    technical_log_purge_interval_hours: int = 24

    # Registre de versions AFNOR (§ 4.8, lot 8) : versions du serveur exposé à Odoo
    # effectivement montées, séparées par des virgules — permet de désactiver/retirer
    # une version sans supprimer son code (dépréciation progressive, § 4.8).
    afnor_api_enabled_versions: str = "v1"

    # Taille maximale acceptée pour un fichier proxifié vers SuperPDP (`POST /flows`,
    # § 4.4) — au-delà, la requête est rejetée (413) avant d'être intégralement
    # chargée en mémoire, pour éviter qu'un client OAuth (malveillant ou compromis)
    # n'épuise la mémoire du process avec un envoi disproportionné.
    max_upload_size_bytes: int = 20 * 1024 * 1024


settings = Settings()
