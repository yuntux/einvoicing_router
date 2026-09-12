from stdnum.fr import siren as siren_stdnum


def _valid_siren(prefix8: str) -> str:
    """Complète un préfixe de 8 chiffres par la clé Luhn qui en fait un SIREN valide
    (les tests ont besoin de SIREN distincts mais valides, pas de vrais SIREN)."""
    for check_digit in range(10):
        candidate = f"{prefix8}{check_digit}"
        if siren_stdnum.is_valid(candidate):
            return candidate
    raise AssertionError(f"Aucune clé Luhn valide pour {prefix8!r}")


def _make_company(client, suffix: str = "0000") -> int:
    resp = client.post(
        "/api/ihm/companies",
        json={"siren": _valid_siren(f"9998{suffix}"), "name": f"Entreprise {suffix}"},
    )
    return resp.json()["id"]


def test_create_partner_and_target_application_and_routing_rule(client):
    partner_resp = client.post(
        "/api/ihm/partners", json={"siren": _valid_siren("98765432"), "name": "Fournisseur SAS"}
    )
    assert partner_resp.status_code == 201
    partner = partner_resp.json()
    company_id = _make_company(client, "0001")

    target_resp = client.post(
        "/api/ihm/target-applications",
        json={
            "name": "Spendesk",
            "routing_method": "mail",
            "company_id": company_id,
            "parameters": {"to": ["ap@spendesk.com"], "cc": [], "bcc": []},
        },
    )
    assert target_resp.status_code == 201
    target = target_resp.json()
    assert target["routing_method"] == "mail"

    rule_resp = client.post(
        "/api/ihm/routing-rules",
        json={
            "partner_directory_id": partner["id"],
            "target_application_id": target["id"],
        },
    )
    assert rule_resp.status_code == 201
    rule = rule_resp.json()
    assert rule["active"] is True

    list_resp = client.get("/api/ihm/routing-rules", params={"partner_id": partner["id"]})
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    resolve_resp = client.get(
        "/api/ihm/routing-rules/resolve",
        params={"siren": partner["siren"], "reference_date": "2026-01-01"},
    )
    assert resolve_resp.status_code == 200
    resolved = resolve_resp.json()
    assert len(resolved) == 1
    assert resolved[0]["id"] == target["id"]


def test_resolve_unknown_siren_returns_empty_list(client):
    resolve_resp = client.get(
        "/api/ihm/routing-rules/resolve",
        params={"siren": "000000000", "reference_date": "2026-01-01"},
    )
    assert resolve_resp.status_code == 200
    assert resolve_resp.json() == []


def test_deactivate_target_application_excludes_it_from_resolve(client):
    partner = client.post(
        "/api/ihm/partners",
        json={"siren": _valid_siren("11122233"), "name": "Fournisseur Désactivable"},
    ).json()
    target = client.post(
        "/api/ihm/target-applications",
        json={
            "name": "Comptable",
            "routing_method": "mail",
            "company_id": _make_company(client, "0002"),
            "parameters": {"to": ["compta@example.com"], "cc": [], "bcc": []},
        },
    ).json()
    assert target["is_active"] is True
    client.post(
        "/api/ihm/routing-rules",
        json={"partner_directory_id": partner["id"], "target_application_id": target["id"]},
    )

    deactivate_resp = client.put(
        f"/api/ihm/target-applications/{target['id']}/status", json={"is_active": False}
    )
    assert deactivate_resp.status_code == 200
    assert deactivate_resp.json()["is_active"] is False

    resolve_resp = client.get(
        "/api/ihm/routing-rules/resolve",
        params={"siren": partner["siren"], "reference_date": "2026-01-01"},
    )
    assert resolve_resp.json() == []

    reactivate_resp = client.put(
        f"/api/ihm/target-applications/{target['id']}/status", json={"is_active": True}
    )
    assert reactivate_resp.json()["is_active"] is True

    resolve_resp = client.get(
        "/api/ihm/routing-rules/resolve",
        params={"siren": partner["siren"], "reference_date": "2026-01-01"},
    )
    assert len(resolve_resp.json()) == 1


def test_update_status_unknown_target_application_returns_404(client):
    response = client.put("/api/ihm/target-applications/999999/status", json={"is_active": False})
    assert response.status_code == 404


def _make_partner_and_target(client, suffix: str):
    partner = client.post(
        "/api/ihm/partners",
        json={"siren": _valid_siren(f"1112{suffix}"), "name": f"Fournisseur {suffix}"},
    ).json()
    target = client.post(
        "/api/ihm/target-applications",
        json={
            "name": f"Cible {suffix}",
            "routing_method": "mail",
            "company_id": _make_company(client, suffix),
            "parameters": {"to": ["ap@example.com"], "cc": [], "bcc": []},
        },
    ).json()
    return partner, target


def test_end_date_before_start_date_is_rejected(client):
    partner, target = _make_partner_and_target(client, "3301")
    response = client.post(
        "/api/ihm/routing-rules",
        json={
            "partner_directory_id": partner["id"],
            "target_application_id": target["id"],
            "start_date": "2026-06-01",
            "end_date": "2026-01-01",
        },
    )
    assert response.status_code == 422


def test_end_date_without_start_date_is_rejected(client):
    partner, target = _make_partner_and_target(client, "3302")
    response = client.post(
        "/api/ihm/routing-rules",
        json={
            "partner_directory_id": partner["id"],
            "target_application_id": target["id"],
            "end_date": "2026-01-01",
        },
    )
    assert response.status_code == 422


def test_upsert_routing_rule_creates_then_updates(client):
    partner, target = _make_partner_and_target(client, "3303")

    create_resp = client.put(
        f"/api/ihm/routing-rules/{partner['id']}/{target['id']}",
        json={"start_date": "2026-01-01"},
    )
    assert create_resp.status_code == 200
    rule = create_resp.json()
    assert rule["start_date"] == "2026-01-01"
    assert rule["end_date"] is None

    list_resp = client.get("/api/ihm/routing-rules", params={"partner_id": partner["id"]})
    assert len(list_resp.json()) == 1

    update_resp = client.put(
        f"/api/ihm/routing-rules/{partner['id']}/{target['id']}",
        json={"start_date": "2026-01-01", "end_date": "2026-12-31"},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["id"] == rule["id"]
    assert updated["end_date"] == "2026-12-31"

    # Toujours une seule règle pour ce couple (mise à jour, pas doublon).
    list_resp = client.get("/api/ihm/routing-rules", params={"partner_id": partner["id"]})
    assert len(list_resp.json()) == 1


def test_upsert_routing_rule_invalid_dates_returns_422(client):
    partner, target = _make_partner_and_target(client, "3304")
    response = client.put(
        f"/api/ihm/routing-rules/{partner['id']}/{target['id']}",
        json={"end_date": "2026-01-01"},
    )
    assert response.status_code == 422


def test_upsert_routing_rule_unknown_partner_returns_404(client):
    _, target = _make_partner_and_target(client, "3305")
    response = client.put(
        f"/api/ihm/routing-rules/999999/{target['id']}",
        json={"start_date": "2026-01-01"},
    )
    assert response.status_code == 404


def test_update_mail_target_application_parameters(client):
    target = client.post(
        "/api/ihm/target-applications",
        json={
            "name": "Spendesk",
            "routing_method": "mail",
            "company_id": _make_company(client, "0010"),
            "parameters": {"to": ["ap@example.com"], "cc": [], "bcc": []},
        },
    ).json()

    update_resp = client.put(
        f"/api/ihm/target-applications/{target['id']}",
        json={
            "name": "Spendesk Renommé",
            "parameters": {"to": ["nouveau@example.com"], "cc": ["copie@example.com"], "bcc": []},
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "Spendesk Renommé"
    assert updated["parameters"]["to"] == ["nouveau@example.com"]
    assert updated["parameters"]["cc"] == ["copie@example.com"]


def test_update_afnor_api_target_application_updates_oauth_application(client):
    company_id = _make_company(client, "0011")
    target = client.post(
        "/api/ihm/target-applications",
        json={
            "name": "Odoo",
            "routing_method": "afnor_api",
            "company_id": company_id,
            "parameters": {
                "redirect_urls": ["https://odoo.example/callback"],
                "preferred_conversion_format": "Factur-X",
                "app_type": "confidential",
                "webhook_url": None,
            },
        },
    ).json()
    assert target["oauth_application"]["preferred_conversion_format"] == "Factur-X"

    update_resp = client.put(
        f"/api/ihm/target-applications/{target['id']}",
        json={
            "name": "Odoo",
            "parameters": {
                "redirect_urls": ["https://odoo.example/callback", "https://odoo.example/other"],
                "preferred_conversion_format": "UBL",
                "app_type": "confidential",
                "webhook_url": "https://odoo.example/webhook",
            },
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["oauth_application"]["preferred_conversion_format"] == "UBL"
    assert updated["oauth_application"]["webhook_url"] == "https://odoo.example/webhook"
    assert updated["oauth_application"]["redirect_urls"] == (
        "https://odoo.example/callback,https://odoo.example/other"
    )
    # client_id/secret ne sont jamais exposés par cet endpoint (§ 4.9.2).
    assert "client_id" not in updated["oauth_application"]


def test_update_unknown_target_application_returns_404(client):
    response = client.put(
        "/api/ihm/target-applications/999999", json={"name": "X", "parameters": {}}
    )
    assert response.status_code == 404
