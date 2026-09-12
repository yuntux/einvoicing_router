"""Fixtures partagées : base SQLite en mémoire (spec.md § 10.2) + client HTTP FastAPI."""

import os

# `Settings.oidc_mode` (app/config.py) n'a volontairement aucune valeur par défaut
# (§ NF3, fail-closed) : la suite de tests choisit explicitement "disabled" ici,
# avant tout import de `app.config`, plutôt que de dépendre d'un défaut silencieux —
# les tests qui veulent exercer l'authentification le surchargent eux-mêmes via
# `monkeypatch.setattr(settings, "oidc_mode", ...)`.
os.environ.setdefault("ROUTER_OIDC_MODE", "disabled")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all ORM models on Base.metadata)
from app.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app


@pytest.fixture(autouse=True)
def _tmp_invoice_storage(tmp_path, monkeypatch):
    """Toutes les factures écrites par les tests vont dans un répertoire temporaire,
    jamais dans le répertoire de stockage réel du projet."""
    monkeypatch.setattr(settings, "invoice_storage_root", str(tmp_path))


@pytest.fixture(autouse=True)
def _disable_scheduler(monkeypatch):
    """Le scheduler définitif (§ 4.7) ne doit jamais démarrer pendant les tests : il
    tournerait dans un thread de fond contre la base réelle (`SessionLocal`), pas
    contre la base SQLite en mémoire propre à chaque test."""
    monkeypatch.setattr(settings, "scheduler_enabled", False)


@pytest.fixture(autouse=True)
def _disable_rate_limit(monkeypatch):
    """La limitation de débit (NF6) sur `/oauth/token`/`/auth/login` est désactivée
    par défaut dans les tests, qui appellent ces endpoints bien plus souvent qu'un
    usage réel (cf. test_rate_limit.py, qui la réactive explicitement)."""
    monkeypatch.setattr(settings, "rate_limit_enabled", False)


@pytest.fixture(autouse=True)
def _disable_ip_allowlist_middleware(monkeypatch):
    """Le middleware d'allowlist IP (NF6, lot 7) interroge la base réelle
    (`SessionLocal`) à chaque requête, hors du mécanisme de substitution `get_db`
    propre aux routes FastAPI — désactivé par défaut dans les tests, qui l'exercent
    directement (cf. test_ip_allowlist.py)."""
    monkeypatch.setattr(settings, "ip_allowlist_enabled", False)


@pytest.fixture(autouse=True)
def _reset_afnor_client_adapter_session_cache():
    """`AfnorClientAdapter` (lot 6) est un singleton process-lifetime qui met en cache
    ses sessions pyfrctc par `company.id` — sans ce nettoyage, une session mise en
    cache par un test polluerait un autre test utilisant une base en mémoire fraîche
    (les IDs y redémarrent à 1 à chaque fois)."""
    from app.afnor.client.adapter import afnor_client_adapter

    afnor_client_adapter._sessions.clear()
    yield
    afnor_client_adapter._sessions.clear()


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_local()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    # `base_url` en https : le cookie de session IHM est `Secure` dès que
    # `oidc_mode != "dev"` (§ NF3) — httpx n'expose/n'envoie un cookie `Secure` que
    # sur une origine https, y compris pour le client de test.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()
