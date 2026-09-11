def test_create_partner_and_target_application_and_routing_rule(client):
    partner_resp = client.post(
        "/api/ihm/partners", json={"siren": "987654321", "name": "Fournisseur SAS"}
    )
    assert partner_resp.status_code == 201
    partner = partner_resp.json()

    target_resp = client.post(
        "/api/ihm/target-applications",
        json={
            "name": "Spendesk",
            "routing_method": "mail",
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
