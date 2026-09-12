"""Consultation des journaux de traçabilité depuis l'IHM (spec.md § 6.1) — jusque-là
écrits par `audit_trace_service` mais jamais relus par aucune page."""

from datetime import date, datetime, timedelta

from app.models.audit import FlowTrace
from app.services import audit_trace_service


def test_list_flow_traces(client, db_session):
    audit_trace_service.record_flow_trace(
        db_session,
        direction="router_to_superpdp",
        afnor_api_version="v1",
        request={"filename": "f.xml"},
        response={"flow_id": "abc"},
        http_status=200,
    )

    response = client.get("/api/ihm/audit/flow-traces")
    assert response.status_code == 200
    [trace] = response.json()
    assert trace["direction"] == "router_to_superpdp"
    assert trace["http_status"] == 200
    assert trace["request"] == {"filename": "f.xml"}


def test_list_technical_logs(client, db_session):
    company = client.post("/api/ihm/companies", json={"siren": "123456782", "name": "Acme"}).json()
    audit_trace_service.record_technical_log(
        db_session,
        log_type="invoice_polling",
        origin="scheduler",
        company_id=company["id"],
        status="success",
        new_count=3,
    )

    response = client.get("/api/ihm/audit/technical-logs")
    assert response.status_code == 200
    [log] = response.json()
    assert log["log_type"] == "invoice_polling"
    assert log["company_id"] == company["id"]
    assert log["new_count"] == 3


def test_list_audit_logs_includes_user_email(client, db_session):
    from app.models.referential import User

    user = User(email="alice@example.com", name="Alice", role="admin", is_active=True)
    db_session.add(user)
    db_session.commit()

    audit_trace_service.record_audit_log(
        db_session, action="invoice_download", target="42", user_id=user.id, ip_address="127.0.0.1"
    )
    audit_trace_service.record_audit_log(
        db_session, action="invoice_download", target="43", user_id=None, ip_address=None
    )

    response = client.get("/api/ihm/audit/audit-logs")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    by_target = {row["target"]: row for row in body}
    assert by_target["42"]["user_email"] == "alice@example.com"
    assert by_target["43"]["user_email"] is None


def test_flow_traces_filters(client, db_session):
    """§ 8.3 : un filtre par colonne, plus des bornes de date comme la page
    Factures."""
    audit_trace_service.record_flow_trace(
        db_session,
        direction="router_to_superpdp",
        afnor_api_version="v1",
        request={},
        response={},
        http_status=200,
    )
    audit_trace_service.record_flow_trace(
        db_session,
        direction="odoo_to_router",
        afnor_api_version="v2",
        request={},
        response={},
        http_status=500,
    )

    assert len(client.get("/api/ihm/audit/flow-traces").json()) == 2

    response = client.get("/api/ihm/audit/flow-traces", params={"direction": "odoo_to_router"})
    [trace] = response.json()
    assert trace["afnor_api_version"] == "v2"

    response = client.get("/api/ihm/audit/flow-traces", params={"http_status": 200})
    [trace] = response.json()
    assert trace["http_status"] == 200

    response = client.get("/api/ihm/audit/flow-traces", params={"afnor_api_version": "v1"})
    assert len(response.json()) == 1

    # Filtre correlation_id : recherche partielle sur un id connu.
    known = client.get("/api/ihm/audit/flow-traces").json()[0]
    partial = known["correlation_id"][:8]
    response = client.get("/api/ihm/audit/flow-traces", params={"correlation_id": partial})
    assert any(t["id"] == known["id"] for t in response.json())


def test_flow_traces_date_range_filter_includes_full_end_day(client, db_session):
    """La borne de fin doit inclure toute la journée (pas seulement minuit) —
    même logique que les filtres de dates de la page Factures."""
    today = date(2026, 3, 15)
    trace = FlowTrace(
        correlation_id="corr-1",
        direction="router_to_superpdp",
        afnor_api_version="v1",
        request={},
        response={},
        http_status=200,
        created_at=datetime.combine(today, datetime.min.time()) + timedelta(hours=23, minutes=59),
    )
    db_session.add(trace)
    db_session.commit()

    response = client.get(
        "/api/ihm/audit/flow-traces",
        params={"created_from": today.isoformat(), "created_to": today.isoformat()},
    )
    assert len(response.json()) == 1

    response = client.get(
        "/api/ihm/audit/flow-traces",
        params={"created_to": (today - timedelta(days=1)).isoformat()},
    )
    assert response.json() == []


def test_technical_logs_filters(client, db_session):
    company_a = client.post("/api/ihm/companies", json={"siren": "123456782", "name": "A"}).json()
    company_b = client.post("/api/ihm/companies", json={"siren": "100000009", "name": "B"}).json()
    audit_trace_service.record_technical_log(
        db_session,
        log_type="invoice_polling",
        origin="scheduler",
        company_id=company_a["id"],
        status="success",
        new_count=3,
        updated_count=1,
    )
    audit_trace_service.record_technical_log(
        db_session,
        log_type="invoice_polling",
        origin="scheduler",
        company_id=company_b["id"],
        status="error",
        new_count=0,
        updated_count=0,
        details="boom",
    )

    response = client.get("/api/ihm/audit/technical-logs", params={"company_id": company_a["id"]})
    [log] = response.json()
    assert log["status"] == "success"

    response = client.get("/api/ihm/audit/technical-logs", params={"status": "error"})
    [log] = response.json()
    assert log["company_id"] == company_b["id"]

    response = client.get("/api/ihm/audit/technical-logs", params={"new_count": 3})
    assert len(response.json()) == 1

    response = client.get("/api/ihm/audit/technical-logs", params={"details": "boo"})
    [log] = response.json()
    assert log["details"] == "boom"


def test_audit_logs_filters(client, db_session):
    from app.models.referential import User

    alice = User(email="alice@example.com", name="Alice", role="admin", is_active=True)
    bob = User(email="bob@example.com", name="Bob", role="user", is_active=True)
    db_session.add_all([alice, bob])
    db_session.commit()

    audit_trace_service.record_audit_log(
        db_session, action="invoice_download", target="42", user_id=alice.id, ip_address="127.0.0.1"
    )
    audit_trace_service.record_audit_log(
        db_session, action="login", target=str(bob.id), user_id=bob.id, ip_address="10.0.0.1"
    )

    response = client.get("/api/ihm/audit/audit-logs", params={"user_email": "alice"})
    [row] = response.json()
    assert row["target"] == "42"

    response = client.get("/api/ihm/audit/audit-logs", params={"action": "login"})
    [row] = response.json()
    assert row["user_email"] == "bob@example.com"

    response = client.get("/api/ihm/audit/audit-logs", params={"target": "42"})
    assert len(response.json()) == 1

    response = client.get("/api/ihm/audit/audit-logs", params={"ip_address": "10.0.0.1"})
    [row] = response.json()
    assert row["action"] == "login"
