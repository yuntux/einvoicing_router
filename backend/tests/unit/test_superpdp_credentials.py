"""API identifiants SuperPDP par entreprise (spec.md § 4.10, lot 6) — le secret n'est
jamais renvoyé une fois enregistré (chiffrement réversible mais confidentiel)."""

from unittest.mock import patch

from app.config import settings
from app.services import superpdp_credentials_service
from app.services.secrets_encryption import decrypt_secret


def _make_company(client):
    response = client.post("/api/ihm/companies", json={"siren": "123456782", "name": "Acheteur"})
    return response.json()["id"]


def test_status_unconfigured_by_default(client):
    company_id = _make_company(client)
    response = client.get(f"/api/ihm/companies/{company_id}/superpdp-credentials")
    assert response.status_code == 200
    assert response.json() == {"configured": False, "client_id": None, "platform": None}


def test_set_credentials_then_status_never_leaks_secret(client, db_session):
    company_id = _make_company(client)

    response = client.put(
        f"/api/ihm/companies/{company_id}/superpdp-credentials",
        json={"client_id": "superpdp-client-1", "client_secret": "s3cret-superpdp"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"configured": True, "client_id": "superpdp-client-1", "platform": None}
    assert "client_secret" not in body
    assert "s3cret-superpdp" not in response.text

    status = client.get(f"/api/ihm/companies/{company_id}/superpdp-credentials")
    assert status.json() == {"configured": True, "client_id": "superpdp-client-1", "platform": None}
    assert "s3cret-superpdp" not in status.text

    application = superpdp_credentials_service.get_credentials_application(
        db_session, company_id=company_id
    )
    assert decrypt_secret(application.client_secret_encrypted) == "s3cret-superpdp"


def test_replacing_credentials_clears_token_cache(client, db_session):
    company_id = _make_company(client)
    client.put(
        f"/api/ihm/companies/{company_id}/superpdp-credentials",
        json={"client_id": "client-a", "client_secret": "secret-a"},
    )
    application = superpdp_credentials_service.get_credentials_application(
        db_session, company_id=company_id
    )
    application.token_cache = '{"access_token": "abc"}'
    db_session.commit()

    client.put(
        f"/api/ihm/companies/{company_id}/superpdp-credentials",
        json={"client_id": "client-b", "client_secret": "secret-b"},
    )
    db_session.refresh(application)
    assert application.client_id == "client-b"
    assert application.token_cache is None


def test_set_credentials_with_known_platform(client, db_session):
    company_id = _make_company(client)

    response = client.put(
        f"/api/ihm/companies/{company_id}/superpdp-credentials",
        json={"client_id": "client-a", "client_secret": "secret-a", "platform": "superpdp"},
    )
    assert response.status_code == 200
    assert response.json() == {"configured": True, "client_id": "client-a", "platform": "superpdp"}

    status = client.get(f"/api/ihm/companies/{company_id}/superpdp-credentials")
    assert status.json()["platform"] == "superpdp"


def test_set_credentials_with_unknown_platform_returns_422(client):
    company_id = _make_company(client)

    response = client.put(
        f"/api/ihm/companies/{company_id}/superpdp-credentials",
        json={"client_id": "client-a", "client_secret": "secret-a", "platform": "not-a-real-platform"},
    )
    assert response.status_code == 422


def test_list_afnor_platforms(client):
    response = client.get("/api/ihm/companies/afnor-platforms")
    assert response.status_code == 200
    keys = [p["key"] for p in response.json()]
    assert "superpdp" in keys


def test_set_credentials_always_tests_connection_ok_in_fake_mode(client, monkeypatch):
    """En mode `fake` (défaut dev/tests), le test de connexion réussit toujours sans
    appel réseau — rien de réel à joindre."""
    monkeypatch.setattr(settings, "superpdp_client_mode", "fake")
    company_id = _make_company(client)

    response = client.put(
        f"/api/ihm/companies/{company_id}/superpdp-credentials",
        json={"client_id": "client-a", "client_secret": "secret-a"},
    )
    assert response.status_code == 200


def test_set_credentials_rejected_when_connection_test_fails(client, db_session, monkeypatch):
    """En mode `pyfrctc` réel, un test de connexion échoué (identifiants invalides,
    réseau indisponible...) empêche l'enregistrement — pas de credentials persistés
    sur la base d'un aller-retour réseau qu'on n'a pas vérifié."""
    monkeypatch.setattr(settings, "superpdp_client_mode", "pyfrctc")
    company_id = _make_company(client)

    with patch(
        "app.services.superpdp_credentials_service.core.get_session",
        side_effect=RuntimeError("invalid_client"),
    ):
        response = client.put(
            f"/api/ihm/companies/{company_id}/superpdp-credentials",
            json={"client_id": "client-a", "client_secret": "wrong-secret"},
        )

    assert response.status_code == 422
    assert "invalid_client" in response.json()["detail"]
    assert superpdp_credentials_service.get_credentials_application(
        db_session, company_id=company_id
    ) is None


def test_set_credentials_accepted_when_connection_test_succeeds(client, monkeypatch):
    monkeypatch.setattr(settings, "superpdp_client_mode", "pyfrctc")
    company_id = _make_company(client)

    with patch(
        "app.services.superpdp_credentials_service.core.get_session", return_value="fake-session"
    ):
        response = client.put(
            f"/api/ihm/companies/{company_id}/superpdp-credentials",
            json={"client_id": "client-a", "client_secret": "secret-a"},
        )

    assert response.status_code == 200
    assert response.json()["configured"] is True
