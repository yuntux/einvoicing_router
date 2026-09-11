from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ROUTER_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./router.db"
    invoice_storage_root: str = "./data/invoices"


settings = Settings()
