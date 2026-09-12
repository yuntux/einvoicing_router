"""API IHM liste des échecs de routage + rejeu manuel en masse (spec.md § 4.7, lot 5)."""

from datetime import date

from app.afnor.client.base import RawInvoice
from app.afnor.client.fake import FakeCertifiedPlatformClient
from app.config import settings
from app.models.invoicing import InvoiceRouting, TransferStatus
from app.models.referential import Company, PartnerDirectory, RoutingMethod, TargetApplication
from app.services import routing_rule_service
from app.services.invoice_ingestion_service import ingest_from_client


def _create_restricted_user_scoped_to(client, *, admin_email, user_email, company_id):
    """Connecté en admin, pré-provisionne `user_email`, le cantonne à `company_id`,
    puis se déconnecte et connecte ce compte restreint (spec.md § NF4)."""
    client.get("/api/ihm/auth/login", params={"email": admin_email}, follow_redirects=False)
    users = client.get("/api/ihm/users").json()
    if not any(u["email"] == user_email for u in users):
        client.post("/api/ihm/users", json={"email": user_email})
    user_id = next(u["id"] for u in client.get("/api/ihm/users").json() if u["email"] == user_email)
    response = client.put(
        f"/api/ihm/users/{user_id}/access",
        json={"role": "user", "company_ids": [company_id], "is_active": True},
    )
    assert response.status_code == 200
    client.post("/api/ihm/auth/logout")
    client.get("/api/ihm/auth/login", params={"email": user_email}, follow_redirects=False)


def _make_company(db, siren="111111111"):
    company = Company(siren=siren, name="Ma Société")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _make_failed_routing(db, *, status: TransferStatus, siren: str, flow_id: str):
    company = _make_company(db, siren=siren)
    target = TargetApplication(
        name="Comptable",
        routing_method=RoutingMethod.MAIL,
        company_id=company.id,
        parameters={"to": ["compta@example.com"], "cc": [], "bcc": []},
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    partner = PartnerDirectory(siren=siren, name="Fournisseur")
    db.add(partner)
    db.commit()
    db.refresh(partner)
    routing_rule_service.set_rule_active(
        db,
        partner_directory_id=partner.id,
        target_application_id=target.id,
        active=True,
    )

    raw = RawInvoice(
        certified_platform_flow_id=flow_id,
        emitter_siren=siren,
        invoice_number=f"F-{flow_id}",
        invoice_date=date(2026, 1, 15),
        file_name=f"F-{flow_id}.pdf",
        file_content=b"%PDF-fake-content",
    )
    result = ingest_from_client(db, company=company, client=FakeCertifiedPlatformClient([raw]))
    invoice = result.created[0]

    routing = (
        db.query(InvoiceRouting)
        .filter(
            InvoiceRouting.invoice_id == invoice.id,
            InvoiceRouting.target_application_id == target.id,
        )
        .one()
    )
    routing.transfer_status = status
    routing.attempt_count = 6
    db.commit()
    db.refresh(routing)
    return routing


def test_list_failed_routings(client, db_session):
    routing = _make_failed_routing(
        db_session, status=TransferStatus.FAILED_FINAL, siren="222222222", flow_id="f1"
    )

    response = client.get("/api/ihm/invoice-routings/failed")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == routing.id
    assert body[0]["transfer_status"] == "failed_final"
    assert body[0]["target_application_name"] == "Comptable"


def test_list_failed_routings_excludes_sent(client, db_session):
    _make_failed_routing(db_session, status=TransferStatus.SENT, siren="333333333", flow_id="f2")

    response = client.get("/api/ihm/invoice-routings/failed")
    assert response.status_code == 200
    assert response.json() == []


def test_replay_routings_bulk(client, db_session):
    routing_a = _make_failed_routing(
        db_session, status=TransferStatus.FAILED_FINAL, siren="444444444", flow_id="f3"
    )
    routing_b = _make_failed_routing(
        db_session, status=TransferStatus.RETRYING, siren="555555555", flow_id="f4"
    )

    response = client.post(
        "/api/ihm/invoice-routings/replay",
        json={"routing_ids": [routing_a.id, routing_b.id]},
    )
    assert response.status_code == 200
    results = {r["routing_id"]: r["success"] for r in response.json()}
    assert set(results.keys()) == {routing_a.id, routing_b.id}

    # Sans serveur SMTP configuré, l'envoi réel échoue : les deux retombent en échec
    # définitif (rejeu manuel = essai unique, § 4.7), plus rejouables dans failed list.
    response = client.get("/api/ihm/invoice-routings/failed")
    statuses = {row["id"]: row["transfer_status"] for row in response.json()}
    assert statuses[routing_a.id] == "failed_final"
    assert statuses[routing_b.id] == "failed_final"


def test_replay_unknown_routing_returns_404(client, db_session):
    response = client.post("/api/ihm/invoice-routings/replay", json={"routing_ids": [999999]})
    assert response.status_code == 404


def test_run_send_cycle_moves_to_send_routing_to_retrying(client, db_session):
    company = _make_company(db_session, siren="666666666")
    target = TargetApplication(
        name="Comptable",
        routing_method=RoutingMethod.MAIL,
        company_id=company.id,
        parameters={"to": ["compta@example.com"], "cc": [], "bcc": []},
    )
    db_session.add(target)
    db_session.commit()
    db_session.refresh(target)

    partner = PartnerDirectory(siren="666666666", name="Fournisseur")
    db_session.add(partner)
    db_session.commit()
    db_session.refresh(partner)
    routing_rule_service.set_rule_active(
        db_session,
        partner_directory_id=partner.id,
        target_application_id=target.id,
        active=True,
    )

    raw = RawInvoice(
        certified_platform_flow_id="flow-cycle",
        emitter_siren="666666666",
        invoice_number="F-cycle",
        invoice_date=date(2026, 1, 15),
        file_name="F-cycle.pdf",
        file_content=b"%PDF-fake-content",
    )
    ingest_from_client(db_session, company=company, client=FakeCertifiedPlatformClient([raw]))

    response = client.get("/api/ihm/invoice-routings/failed")
    assert response.json() == []

    response = client.post("/api/ihm/invoice-routings/run-send-cycle")
    assert response.status_code == 204

    response = client.get("/api/ihm/invoice-routings/failed")
    body = response.json()
    assert len(body) == 1
    assert body[0]["transfer_status"] == "retrying"
    assert body[0]["attempt_count"] == 1


def test_restricted_user_sees_only_failed_routings_of_their_company_scope(client, db_session, monkeypatch):
    """§ NF4/§ 5.1 : un utilisateur restreint ne voit que les échecs de routage des
    entreprises pour lesquelles il est habilité, et ne peut pas rejouer un routage
    hors de son périmètre."""
    monkeypatch.setattr(settings, "oidc_mode", "dev")

    routing_own = _make_failed_routing(
        db_session, status=TransferStatus.FAILED_FINAL, siren="777777771", flow_id="f-own"
    )
    routing_other = _make_failed_routing(
        db_session, status=TransferStatus.FAILED_FINAL, siren="777777772", flow_id="f-other"
    )

    _create_restricted_user_scoped_to(
        client,
        admin_email="admin-fr@example.com",
        user_email="user-fr@example.com",
        company_id=routing_own.invoice.company_id,
    )

    response = client.get("/api/ihm/invoice-routings/failed")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [routing_own.id]

    # Rejeu de son propre périmètre : autorisé.
    response = client.post(
        "/api/ihm/invoice-routings/replay", json={"routing_ids": [routing_own.id]}
    )
    assert response.status_code == 200

    # Rejeu d'un routage hors périmètre : refusé, même si l'id est connu.
    response = client.post(
        "/api/ihm/invoice-routings/replay", json={"routing_ids": [routing_other.id]}
    )
    assert response.status_code == 403


def test_failed_routings_filters(client, db_session):
    """§ 8.3 : un filtre par colonne du tableau des échecs de routage."""
    retrying = _make_failed_routing(
        db_session, status=TransferStatus.RETRYING, siren="888888881", flow_id="f-retry"
    )
    final = _make_failed_routing(
        db_session, status=TransferStatus.FAILED_FINAL, siren="888888882", flow_id="f-final"
    )

    response = client.get(
        "/api/ihm/invoice-routings/failed", params={"invoice_number": retrying.invoice.invoice_number}
    )
    assert [r["id"] for r in response.json()] == [retrying.id]

    response = client.get(
        "/api/ihm/invoice-routings/failed", params={"emitter_siren": "888888882"}
    )
    assert [r["id"] for r in response.json()] == [final.id]

    response = client.get(
        "/api/ihm/invoice-routings/failed", params={"target_application_name": "compt"}
    )
    assert {r["id"] for r in response.json()} == {retrying.id, final.id}

    response = client.get(
        "/api/ihm/invoice-routings/failed", params={"transfer_status": "failed_final"}
    )
    assert [r["id"] for r in response.json()] == [final.id]

    response = client.get(
        "/api/ihm/invoice-routings/failed", params={"attempt_count": retrying.attempt_count}
    )
    assert retrying.id in {r["id"] for r in response.json()}
