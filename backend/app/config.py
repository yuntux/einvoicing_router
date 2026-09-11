from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ROUTER_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./router.db"
    invoice_storage_root: str = "./data/invoices"

    # Signature des jetons d'accès émis pour l'API AFNOR exposée aux consommateurs
    # (§ 4.4/§ 4.10). À surcharger via ROUTER_JWT_SECRET en dehors du développement local.
    jwt_secret: str = "dev-insecure-secret-change-me"
    jwt_expiry_seconds: int = 3600


settings = Settings()
