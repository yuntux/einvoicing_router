"""Allowlist IPv4/IPv6 (spec.md NF6, lot 7)."""

from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.ip_allowlist import is_ip_allowed
from app.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.settings import RouterSettings


def test_is_ip_allowed_empty_allowlist_allows_everything():
    assert is_ip_allowed("203.0.113.5", None) is True
    assert is_ip_allowed("203.0.113.5", "") is True
    assert is_ip_allowed("203.0.113.5", "   ") is True


def test_is_ip_allowed_exact_match():
    assert is_ip_allowed("203.0.113.5", "203.0.113.5") is True
    assert is_ip_allowed("203.0.113.6", "203.0.113.5") is False


def test_is_ip_allowed_cidr_match():
    assert is_ip_allowed("203.0.113.42", "203.0.113.0/24") is True
    assert is_ip_allowed("198.51.100.1", "203.0.113.0/24") is False


def test_is_ip_allowed_multiple_entries():
    allowlist = "203.0.113.0/24, 198.51.100.7"
    assert is_ip_allowed("198.51.100.7", allowlist) is True
    assert is_ip_allowed("203.0.113.10", allowlist) is True
    assert is_ip_allowed("192.0.2.1", allowlist) is False


def test_is_ip_allowed_ipv6():
    assert is_ip_allowed("2001:db8::1", "2001:db8::/32") is True
    assert is_ip_allowed("2001:db9::1", "2001:db8::/32") is False


def test_is_ip_allowed_invalid_ip_rejected():
    assert is_ip_allowed("not-an-ip", "203.0.113.0/24") is False


def test_middleware_blocks_disallowed_ihm_ip(monkeypatch):
    """Exerce le middleware réellement monté sur l'app, avec `SessionLocal` redirigée
    vers une base en mémoire dédiée (le middleware n'utilise pas `get_db`, cf. sa
    docstring — désactivé par défaut dans conftest.py pour cette raison)."""
    monkeypatch.setattr(settings, "ip_allowlist_enabled", True)

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine)

    session = session_local()
    session.add(RouterSettings(id=1, ihm_ip_allowlist="203.0.113.5"))
    session.commit()
    session.close()

    monkeypatch.setattr("app.auth.ip_allowlist.SessionLocal", session_local)

    app = create_app()

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        response = test_client.get("/api/ihm/companies")

    assert response.status_code == 403


def test_middleware_allows_configured_ip(monkeypatch):
    monkeypatch.setattr(settings, "ip_allowlist_enabled", True)

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine)

    session = session_local()
    session.add(RouterSettings(id=1, ihm_ip_allowlist="203.0.113.5"))
    session.commit()
    session.close()

    monkeypatch.setattr("app.auth.ip_allowlist.SessionLocal", session_local)

    app = create_app()

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # `client=` force l'adresse vue par le serveur ASGI (par défaut "testclient", qui
    # n'est pas une IP valide) à une adresse réellement présente dans l'allowlist.
    with TestClient(app, client=("203.0.113.5", 12345)) as test_client:
        response = test_client.get("/api/ihm/companies")

    assert response.status_code == 200


def test_middleware_never_blocks_auth_routes(monkeypatch):
    """`/api/ihm/auth/*` doit rester joignable même hors allowlist IHM — sinon
    personne ne pourrait jamais se connecter."""
    monkeypatch.setattr(settings, "ip_allowlist_enabled", True)

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine)

    session = session_local()
    session.add(RouterSettings(id=1, ihm_ip_allowlist="203.0.113.5"))
    session.commit()
    session.close()

    monkeypatch.setattr("app.auth.ip_allowlist.SessionLocal", session_local)

    app = create_app()

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        response = test_client.get("/api/ihm/auth/me")

    assert response.status_code == 200
