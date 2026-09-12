"""Consultation des journaux de traçabilité depuis l'IHM (spec.md § 6.1) — jusque-là
écrits par `audit_trace_service` mais jamais relus par aucune page."""

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
