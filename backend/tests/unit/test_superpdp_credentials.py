"""API identifiants SuperPDP par entreprise (spec.md § 4.10, lot 6) — le secret n'est
jamais renvoyé une fois enregistré (chiffrement réversible mais confidentiel)."""

from app.services import superpdp_credentials_service
from app.services.secrets_encryption import decrypt_secret


def _make_company(client):
    response = client.post("/api/ihm/companies", json={"siren": "123456789", "name": "Acheteur"})
    return response.json()["id"]


def test_status_unconfigured_by_default(client):
    company_id = _make_company(client)
    response = client.get(f"/api/ihm/companies/{company_id}/superpdp-credentials")
    assert response.status_code == 200
    assert response.json() == {"configured": False, "client_id": None}


def test_set_credentials_then_status_never_leaks_secret(client, db_session):
    company_id = _make_company(client)

    response = client.put(
        f"/api/ihm/companies/{company_id}/superpdp-credentials",
        json={"client_id": "superpdp-client-1", "client_secret": "s3cret-superpdp"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"configured": True, "client_id": "superpdp-client-1"}
    assert "client_secret" not in body
    assert "s3cret-superpdp" not in response.text

    status = client.get(f"/api/ihm/companies/{company_id}/superpdp-credentials")
    assert status.json() == {"configured": True, "client_id": "superpdp-client-1"}
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
