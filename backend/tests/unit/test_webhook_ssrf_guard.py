"""Garde-fou anti-SSRF (CWE-918) sur `webhook_url` exposé via l'API IHM des
applications cibles (§ 4.4/§ 4.9.2) — complète test_url_validation.py (fonction
pure) en vérifiant le rejet HTTP bout en bout."""

from stdnum.fr import siren as siren_stdnum


def _valid_siren(prefix8: str) -> str:
    for check_digit in range(10):
        candidate = f"{prefix8}{check_digit}"
        if siren_stdnum.is_valid(candidate):
            return candidate
    raise AssertionError(f"Aucune clé Luhn valide pour {prefix8!r}")


def _make_company(client, suffix: str) -> int:
    resp = client.post(
        "/api/ihm/companies",
        json={"siren": _valid_siren(f"9997{suffix}"), "name": f"Entreprise {suffix}"},
    )
    return resp.json()["id"]


def test_create_target_application_rejects_internal_webhook_url(client):
    company_id = _make_company(client, "0001")

    response = client.post(
        "/api/ihm/target-applications",
        json={
            "name": "Odoo",
            "routing_method": "afnor_api",
            "company_id": company_id,
            "parameters": {
                "redirect_urls": [],
                "preferred_conversion_format": None,
                "app_type": "confidential",
                "webhook_url": "http://169.254.169.254/latest/meta-data/",
            },
        },
    )

    assert response.status_code == 422


def test_create_target_application_rejects_loopback_webhook_url(client):
    company_id = _make_company(client, "0002")

    response = client.post(
        "/api/ihm/target-applications",
        json={
            "name": "Odoo",
            "routing_method": "afnor_api",
            "company_id": company_id,
            "parameters": {
                "redirect_urls": [],
                "preferred_conversion_format": None,
                "app_type": "confidential",
                "webhook_url": "http://127.0.0.1:8000/admin",
            },
        },
    )

    assert response.status_code == 422


def test_update_target_application_rejects_internal_webhook_url(client):
    company_id = _make_company(client, "0003")
    target = client.post(
        "/api/ihm/target-applications",
        json={
            "name": "Odoo",
            "routing_method": "afnor_api",
            "company_id": company_id,
            "parameters": {
                "redirect_urls": [],
                "preferred_conversion_format": None,
                "app_type": "confidential",
                "webhook_url": None,
            },
        },
    ).json()

    response = client.put(
        f"/api/ihm/target-applications/{target['id']}",
        json={
            "name": "Odoo",
            "parameters": {
                "redirect_urls": [],
                "preferred_conversion_format": None,
                "app_type": "confidential",
                "webhook_url": "http://10.0.0.5/internal-hook",
            },
        },
    )

    assert response.status_code == 422


def test_create_target_application_without_webhook_url_still_works(client):
    """La validation ne se déclenche que si un webhook est effectivement fourni."""
    company_id = _make_company(client, "0004")

    response = client.post(
        "/api/ihm/target-applications",
        json={
            "name": "Odoo",
            "routing_method": "afnor_api",
            "company_id": company_id,
            "parameters": {
                "redirect_urls": [],
                "preferred_conversion_format": None,
                "app_type": "confidential",
                "webhook_url": None,
            },
        },
    )

    assert response.status_code == 201
