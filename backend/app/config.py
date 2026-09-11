from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ROUTER_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./router.db"
    invoice_storage_root: str = "./data/invoices"

    # Signature des jetons d'accès émis pour l'API AFNOR exposée aux consommateurs
    # (§ 4.4/§ 4.10). À surcharger via ROUTER_JWT_SECRET en dehors du développement local.
    jwt_secret: str = "dev-insecure-secret-change-me"
    jwt_expiry_seconds: int = 3600

    # Scheduler définitif (§ 4.7) : cycle de rejeu automatique des envois en échec.
    # Désactivé dans les tests (cf. conftest.py) pour ne pas démarrer de thread de fond
    # contre la base réelle pendant l'exécution de la suite.
    scheduler_enabled: bool = True
    retry_interval_minutes: int = 30

    # Client AFNOR côté SuperPDP (§ 4.1/§ 4.8, lot 6) : "fake" (fixtures, défaut dev/tests)
    # ou "pyfrctc" (client réel, nécessite des identifiants SuperPDP par entreprise).
    superpdp_client_mode: str = "fake"
    superpdp_platform: str = "superpdp"
    # Serveur Saxon pour la validation schématron des CDAR (optionnel, § 4.2/NF7) —
    # sans lui, seule la validation XSD (locale, sans réseau) est effectuée.
    saxon_server_url: str | None = None
    polling_interval_minutes: int = 15
    webhook_timeout_seconds: int = 10

    # Clé de chiffrement symétrique des secrets client SuperPDP par entreprise
    # (`OAuthApplication.client_secret_encrypted`, scope router_to_superpdp, § 4.10) —
    # réutilise `jwt_secret` par défaut ; une clé dédiée est recommandée en production
    # (durcissement prévu avec l'authentification réelle, lot 7).
    secrets_encryption_key: str | None = None


settings = Settings()
