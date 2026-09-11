def test_create_and_list_company(client):
    response = client.post("/api/ihm/companies", json={"siren": "123456789", "name": "Acme SAS"})
    assert response.status_code == 201
    created = response.json()
    assert created["siren"] == "123456789"
    assert created["name"] == "Acme SAS"
    assert created["id"] is not None

    response = client.get("/api/ihm/companies")
    assert response.status_code == 200
    companies = response.json()
    assert len(companies) == 1
    assert companies[0]["siren"] == "123456789"


def test_list_companies_empty(client):
    response = client.get("/api/ihm/companies")
    assert response.status_code == 200
    assert response.json() == []
