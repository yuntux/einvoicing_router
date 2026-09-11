"""client_factory — sélection fake/pyfrctc selon settings.superpdp_client_mode
(spec.md § 4.1/§ 4.8, lot 6)."""

from unittest.mock import patch

from app.afnor.client.fake import FakeSuperPDPClient
from app.afnor.client.pyfrctc_client import PyfrctcSuperPDPClient
from app.config import settings
from app.models.referential import Company
from app.services.client_factory import resolve_client_for_company


def test_resolve_client_fake_mode_returns_fake_client(db_session, monkeypatch):
    monkeypatch.setattr(settings, "superpdp_client_mode", "fake")
    company = Company(siren="123456789", name="Test")
    db_session.add(company)
    db_session.commit()

    client = resolve_client_for_company(db_session, company)
    assert isinstance(client, FakeSuperPDPClient)


def test_resolve_client_pyfrctc_mode_returns_pyfrctc_client(db_session, monkeypatch):
    monkeypatch.setattr(settings, "superpdp_client_mode", "pyfrctc")
    company = Company(siren="123456789", name="Test")
    db_session.add(company)
    db_session.commit()

    with patch("app.afnor.client.adapter.core.get_session", return_value="fake-session"):
        from app.services import superpdp_credentials_service

        superpdp_credentials_service.set_credentials(
            db_session, company_id=company.id, client_id="cid", client_secret="csecret"
        )
        client = resolve_client_for_company(db_session, company)

    assert isinstance(client, PyfrctcSuperPDPClient)
