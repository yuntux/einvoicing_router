from stdnum.fr import siren as siren_stdnum


def _valid_siren(prefix8: str) -> str:
    """Complète un préfixe de 8 chiffres par la clé Luhn qui en fait un SIREN valide
    (les tests ont besoin de SIREN distincts mais valides, pas de vrais SIREN)."""
    for check_digit in range(10):
        candidate = f"{prefix8}{check_digit}"
        if siren_stdnum.is_valid(candidate):
            return candidate
    raise AssertionError(f"Aucune clé Luhn valide pour {prefix8!r}")


def test_simulate_reception_and_list_with_filters(client):
    company_resp = client.post(
        "/api/ihm/companies", json={"siren": "333333334", "name": "Ma Société"}
    )
    company = company_resp.json()

    simulate_resp = client.post(
        "/api/test/invoices/simulate",
        json={
            "company_id": company["id"],
            "emitter_siren": "444444442",
            "invoice_number": "F-2026-042",
            "invoice_date": "2026-03-01",
            "amount_total": 1200.50,
            "currency": "EUR",
        },
    )
    assert simulate_resp.status_code == 201
    invoice = simulate_resp.json()
    assert invoice["emitter_siren"] == "444444442"
    assert invoice["amount_total"] == 1200.50

    list_resp = client.get("/api/ihm/invoices", params={"emitter_siren": "444444442"})
    assert list_resp.status_code == 200
    invoices = list_resp.json()
    assert len(invoices) == 1
    assert invoices[0]["invoice_number"] == "F-2026-042"

    detail_resp = client.get(f"/api/ihm/invoices/{invoice['id']}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["routings"] == []
    # § 4.4 : l'émetteur inconnu est ajouté automatiquement à l'annuaire à la
    # réception (nom placeholder, pas de lookup SIRENE), plutôt que de rester
    # rattaché à aucune entrée `PartnerDirectory`.
    assert detail["emitter_name"] == "Fournisseur 444444442 (à compléter)"


def test_list_invoices_filter_no_match(client):
    response = client.get("/api/ihm/invoices", params={"emitter_siren": "999999999"})
    assert response.status_code == 200
    assert response.json() == []


def test_list_invoices_filter_by_emitter_name(client):
    company_siren = _valid_siren("33333399")
    emitter_siren = _valid_siren("44444499")
    company = client.post(
        "/api/ihm/companies", json={"siren": company_siren, "name": "Ma Société"}
    ).json()
    client.post(
        "/api/ihm/partners", json={"siren": emitter_siren, "name": "Fournisseur Alpha SAS"}
    )
    simulate_resp = client.post(
        "/api/test/invoices/simulate",
        json={
            "company_id": company["id"],
            "emitter_siren": emitter_siren,
            "invoice_number": "F-ALPHA-1",
            "invoice_date": "2026-03-01",
        },
    )
    assert simulate_resp.status_code == 201

    # Recherche partielle, insensible à la casse (§ 8.3).
    match_resp = client.get("/api/ihm/invoices", params={"emitter_name": "alpha"})
    assert match_resp.status_code == 200
    matched = match_resp.json()
    assert len(matched) == 1
    assert matched[0]["invoice_number"] == "F-ALPHA-1"

    no_match_resp = client.get("/api/ihm/invoices", params={"emitter_name": "Beta"})
    assert no_match_resp.json() == []


def test_get_invoice_not_found(client):
    response = client.get("/api/ihm/invoices/999999")
    assert response.status_code == 404


def test_list_invoices_includes_routings_for_badges(client, db_session):
    """§ 4.7/§ 8.3 : la liste des factures porte `routings` (statut de transfert par
    application cible) — utilisé par l'IHM pour afficher un badge par application,
    sans passer par le détail de chaque facture."""
    from datetime import date

    from app.models.invoicing import Invoice, InvoiceRouting, TransferStatus
    from app.models.referential import Company, RoutingMethod, TargetApplication

    company = Company(siren=_valid_siren("36111111"), name="Société Badges")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    target = TargetApplication(
        name="Comptable",
        routing_method=RoutingMethod.MAIL,
        company_id=company.id,
        parameters={"to": ["compta@example.com"]},
    )
    db_session.add(target)
    db_session.commit()
    db_session.refresh(target)

    invoice = Invoice(
        company_id=company.id,
        emitter_siren=_valid_siren("37111111"),
        invoice_number="F-BADGE-1",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/badge.pdf",
        certified_platform_flow_id="flow-badge-1",
    )
    db_session.add(invoice)
    db_session.commit()
    db_session.refresh(invoice)

    db_session.add(
        InvoiceRouting(
            invoice_id=invoice.id,
            target_application_id=target.id,
            transfer_status=TransferStatus.RETRYING,
            attempt_count=2,
        )
    )
    db_session.commit()

    response = client.get("/api/ihm/invoices", params={"invoice_number": "F-BADGE-1"})
    assert response.status_code == 200
    [row] = response.json()
    assert len(row["routings"]) == 1
    assert row["routings"][0]["target_application_id"] == target.id
    assert row["routings"][0]["transfer_status"] == "retrying"
    assert row["routings"][0]["attempt_count"] == 2


def test_list_invoices_includes_emitter_and_company_names(client, db_session):
    """La colonne Émetteur/Destinataire de la liste (§ 8.3) a besoin de la raison
    sociale de l'émetteur (PartnerDirectory) et de celle de l'entreprise réceptrice
    (Company), pas seulement de leurs SIREN — jointures faites côté liste, jamais
    dénormalisées sur Invoice."""
    from datetime import date

    from app.models.invoicing import Invoice
    from app.models.referential import Company, PartnerDirectory

    company = Company(siren=_valid_siren("38111111"), name="Tricatel")
    db_session.add(company)
    partner = PartnerDirectory(siren=_valid_siren("39111111"), name="Fournisseur Connu")
    db_session.add(partner)
    db_session.commit()
    db_session.refresh(company)
    db_session.refresh(partner)

    invoice = Invoice(
        company_id=company.id,
        partner_directory_id=partner.id,
        emitter_siren=partner.siren,
        invoice_number="F-NAMES-1",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/names.pdf",
        certified_platform_flow_id="flow-names-1",
    )
    db_session.add(invoice)
    db_session.commit()

    response = client.get("/api/ihm/invoices", params={"invoice_number": "F-NAMES-1"})
    assert response.status_code == 200
    [row] = response.json()
    assert row["emitter_name"] == "Fournisseur Connu"
    assert row["company_name"] == "Tricatel"
    assert row["company_siren"] == company.siren

    detail_response = client.get(f"/api/ihm/invoices/{row['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["emitter_name"] == "Fournisseur Connu"
    assert detail["company_name"] == "Tricatel"
    assert detail["company_siren"] == company.siren


def test_list_invoices_routings_empty_when_unrouted(client, db_session):
    """Aucune règle n'a résolu de cible pour cette facture : `routings` doit être
    vide (l'IHM en déduit le badge "Facture non routée")."""
    from datetime import date

    from app.models.invoicing import Invoice
    from app.models.referential import Company

    company = Company(siren=_valid_siren("38111111"), name="Société Sans Règle")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    invoice = Invoice(
        company_id=company.id,
        emitter_siren=_valid_siren("39111111"),
        invoice_number="F-UNROUTED-1",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/unrouted.pdf",
        certified_platform_flow_id="flow-unrouted-1",
    )
    db_session.add(invoice)
    db_session.commit()

    response = client.get("/api/ihm/invoices", params={"invoice_number": "F-UNROUTED-1"})
    assert response.status_code == 200
    [row] = response.json()
    assert row["routings"] == []
