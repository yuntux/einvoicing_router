"""Rôle « lecture seule » (spec.md § 5.1) : même périmètre entreprises que le rôle
`user` (« restreint »), mais aucune écriture possible — ni sur les pages ouvertes aux
deux rôles (Factures, Règles de routage, Échecs de routage), ni bien sûr sur les pages
admin-only (déjà couvertes par `test_admin_only_pages_scope.py`, comportement
identique pour `readonly`)."""

from datetime import date

from stdnum.fr import siren as siren_stdnum

from app.afnor.client.base import RawInvoice
from app.afnor.client.fake import FakeCertifiedPlatformClient
from app.config import settings
from app.models.invoicing import Invoice, InvoiceRouting, TransferStatus
from app.models.referential import Company, PartnerDirectory, RoutingMethod, TargetApplication
from app.services import routing_rule_service
from app.services.invoice_ingestion_service import ingest_from_client


def _valid_siren(prefix8: str) -> str:
    for check_digit in range(10):
        candidate = f"{prefix8}{check_digit}"
        if siren_stdnum.is_valid(candidate):
            return candidate
    raise AssertionError(f"Aucune clé Luhn valide pour {prefix8!r}")


def _login_as_first_admin(client, email="admin@example.com"):
    client.get("/api/ihm/auth/login", params={"email": email}, follow_redirects=False)


def _create_readonly_user_scoped_to(client, *, admin_email, user_email, company_id):
    users = client.get("/api/ihm/users").json()
    if not any(u["email"] == user_email for u in users):
        client.post("/api/ihm/users", json={"email": user_email})
    user_id = next(u["id"] for u in client.get("/api/ihm/users").json() if u["email"] == user_email)
    response = client.put(
        f"/api/ihm/users/{user_id}/access",
        json={"role": "readonly", "company_ids": [company_id], "is_active": True},
    )
    assert response.status_code == 200
    client.post("/api/ihm/auth/logout")
    client.get("/api/ihm/auth/login", params={"email": user_email}, follow_redirects=False)


def _make_company(client, siren, name):
    response = client.post("/api/ihm/companies", json={"siren": siren, "name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _make_invoice(db, *, company_id, emitter_siren, invoice_number="F-100", flow_id="flow-1"):
    """Insertion directe (plutôt que `/api/test/invoices/simulate`, cf.
    `app.api.testing.invoices`) : cet endpoint n'est monté que si
    `settings.certified_platform_client_mode == "fake"` au démarrage de l'app, ce qui
    dépend de l'environnement d'exécution — l'insertion directe rend ce test
    indépendant de ce réglage."""
    invoice = Invoice(
        company_id=company_id,
        emitter_siren=emitter_siren,
        invoice_number=invoice_number,
        invoice_date=date(2026, 2, 1),
        file_path="unused-for-this-test",
        certified_platform_flow_id=flow_id,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def _make_failed_routing(db, *, status: TransferStatus, company_id: int, siren: str, flow_id: str):
    company = db.get(Company, company_id)
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
        db, partner_directory_id=partner.id, target_application_id=target.id, active=True
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
        .filter(InvoiceRouting.invoice_id == invoice.id, InvoiceRouting.target_application_id == target.id)
        .one()
    )
    routing.transfer_status = status
    routing.attempt_count = 6
    db.commit()
    db.refresh(routing)
    return routing


def test_readonly_user_can_read_invoices_and_routing_pages(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin1@example.com")
    company_a = _make_company(client, _valid_siren("41111111"), "Société A")
    _make_invoice(db_session, company_id=company_a, emitter_siren=_valid_siren("41111112"))

    _create_readonly_user_scoped_to(
        client, admin_email="admin1@example.com", user_email="reader1@example.com", company_id=company_a
    )

    assert client.get("/api/ihm/invoices").status_code == 200
    assert client.get("/api/ihm/routing-rules").status_code == 200
    assert client.get("/api/ihm/invoice-routings/failed").status_code == 200
    assert client.get("/api/ihm/partners").status_code == 200


def test_readonly_user_cannot_create_lifecycle_event(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin2@example.com")
    company_a = _make_company(client, _valid_siren("42111111"), "Société A")
    invoice = _make_invoice(db_session, company_id=company_a, emitter_siren=_valid_siren("42111112"))

    _create_readonly_user_scoped_to(
        client, admin_email="admin2@example.com", user_email="reader2@example.com", company_id=company_a
    )

    response = client.post(
        f"/api/ihm/invoices/{invoice.id}/lifecycle-events", json={"status": "approved"}
    )
    assert response.status_code == 403


def test_readonly_user_cannot_toggle_routing_rule(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin3@example.com")
    company_a = _make_company(client, _valid_siren("43111111"), "Société A")

    target = TargetApplication(
        name="Comptable",
        routing_method=RoutingMethod.MAIL,
        company_id=company_a,
        parameters={"to": ["compta@example.com"], "cc": [], "bcc": []},
    )
    db_session.add(target)
    partner = PartnerDirectory(siren=_valid_siren("43111112"), name="Fournisseur")
    db_session.add(partner)
    db_session.commit()
    db_session.refresh(target)
    db_session.refresh(partner)

    _create_readonly_user_scoped_to(
        client, admin_email="admin3@example.com", user_email="reader3@example.com", company_id=company_a
    )

    response = client.put(
        f"/api/ihm/routing-rules/{partner.id}/{target.id}",
        json={"active": True, "reroute_existing": False},
    )
    assert response.status_code == 403


def test_readonly_user_cannot_create_partner(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin4@example.com")
    company_a = _make_company(client, _valid_siren("44111111"), "Société A")

    _create_readonly_user_scoped_to(
        client, admin_email="admin4@example.com", user_email="reader4@example.com", company_id=company_a
    )

    response = client.post(
        "/api/ihm/partners", json={"siren": _valid_siren("44111112"), "name": "Fournisseur"}
    )
    assert response.status_code == 403


def test_readonly_user_cannot_replay_routing_or_force_send_cycle(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin5@example.com")
    company_a = _make_company(client, _valid_siren("45111111"), "Société A")
    routing = _make_failed_routing(
        db_session,
        status=TransferStatus.FAILED_FINAL,
        company_id=company_a,
        siren=_valid_siren("45111112"),
        flow_id="ro1",
    )

    _create_readonly_user_scoped_to(
        client, admin_email="admin5@example.com", user_email="reader5@example.com", company_id=company_a
    )

    replay_response = client.post(
        "/api/ihm/invoice-routings/replay", json={"routing_ids": [routing.id]}
    )
    assert replay_response.status_code == 403

    cycle_response = client.post("/api/ihm/invoice-routings/run-send-cycle")
    assert cycle_response.status_code == 403


def test_readonly_user_is_still_company_scoped_like_restricted_user(client, monkeypatch):
    """Le rôle `readonly` réutilise le même périmètre (`allowed_company_ids`) que
    `user` (§ 6.1) : les mêmes pages admin-only lui restent fermées."""
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin6@example.com")
    company_a = _make_company(client, _valid_siren("46111111"), "Société A")

    _create_readonly_user_scoped_to(
        client, admin_email="admin6@example.com", user_email="reader6@example.com", company_id=company_a
    )

    assert client.get("/api/ihm/companies").status_code == 403
    assert client.get("/api/ihm/settings").status_code == 403
    assert client.get("/api/ihm/audit/flow-traces").status_code == 403


def test_admin_can_still_write_after_readonly_role_added(client, monkeypatch):
    """Non-régression : l'ajout de `require_write` ne bloque pas les admins ni le rôle
    `user` (« restreint »)."""
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin7@example.com")

    response = client.post(
        "/api/ihm/partners", json={"siren": _valid_siren("47111111"), "name": "Fournisseur"}
    )
    assert response.status_code == 201
