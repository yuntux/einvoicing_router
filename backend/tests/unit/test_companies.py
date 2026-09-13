def test_create_and_list_company(client):
    response = client.post("/api/ihm/companies", json={"siren": "123456782", "name": "Acme SAS"})
    assert response.status_code == 201
    created = response.json()
    assert created["siren"] == "123456782"
    assert created["name"] == "Acme SAS"
    assert created["id"] is not None

    response = client.get("/api/ihm/companies")
    assert response.status_code == 200
    companies = response.json()
    assert len(companies) == 1
    assert companies[0]["siren"] == "123456782"


def test_list_companies_empty(client):
    response = client.get("/api/ihm/companies")
    assert response.status_code == 200
    assert response.json() == []


def test_lookup_certified_platform_configured_filters_by_verified_connection(client, db_session):
    """`?certified_platform_configured=true` (§ écran Annuaire) ne retourne que les
    entreprises dont la connexion a déjà été validée avec succès
    (`certified_platform_connection_verified_at` renseigné) — la seule présence de
    `certified_platform_client_id` ne suffit pas (régression : une entreprise avec
    des identifiants bidon/jamais testés apparaissait quand même dans la liste)."""
    from datetime import datetime

    from app.models.referential import Company

    verified = Company(siren="123456789", name="Vérifiée")
    verified.certified_platform_client_id = "cid"
    verified.certified_platform_connection_verified_at = datetime.utcnow()
    db_session.add(verified)

    configured_not_verified = Company(siren="111111118", name="Configurée mais jamais testée")
    configured_not_verified.certified_platform_client_id = "bidon"
    db_session.add(configured_not_verified)

    db_session.add(Company(siren="987654321", name="Pas configurée"))
    db_session.commit()

    response = client.get("/api/ihm/companies/lookup", params={"certified_platform_configured": "true"})

    assert response.status_code == 200
    assert [c["name"] for c in response.json()] == ["Vérifiée"]

    response_all = client.get("/api/ihm/companies/lookup")
    assert response_all.status_code == 200
    assert len(response_all.json()) == 3
