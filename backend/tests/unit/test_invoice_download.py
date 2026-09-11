"""Téléchargement de facture + AuditLog + jointure dernier téléchargement
(spec.md § 4.2/§ 8.3/NF9, lot 8)."""

from datetime import date

from app.afnor.client.base import RawInvoice
from app.afnor.client.fake import FakeSuperPDPClient
from app.models.audit import AuditLog
from app.models.referential import Company
from app.services.invoice_ingestion_service import ingest_from_client


def _make_invoice(db, company):
    raw = RawInvoice(
        superpdp_flow_id="flow-dl-1",
        emitter_siren="987654321",
        invoice_number="F-dl-1",
        invoice_date=date(2026, 1, 1),
        file_name="F-dl-1.pdf",
        file_content=b"%PDF-fake-content",
    )
    result = ingest_from_client(db, company=company, client=FakeSuperPDPClient([raw]))
    return result.created[0]


def _make_company(client, siren="123456789"):
    response = client.post("/api/ihm/companies", json={"siren": siren, "name": "Ma Société"})
    return response.json()["id"]


def test_download_invoice_returns_file_and_records_audit_log(client, db_session):
    company_id = _make_company(client)
    company = db_session.get(Company, company_id)
    invoice = _make_invoice(db_session, company)

    response = client.get(f"/api/ihm/invoices/{invoice.id}/download")
    assert response.status_code == 200
    assert response.content == b"%PDF-fake-content"

    logs = db_session.query(AuditLog).filter(AuditLog.action == "invoice_download").all()
    assert len(logs) == 1
    assert logs[0].target == str(invoice.id)
    assert logs[0].user_id is None  # oidc_mode=disabled par défaut


def test_invoice_detail_shows_last_download_via_join(client, db_session):
    company_id = _make_company(client)
    company = db_session.get(Company, company_id)
    invoice = _make_invoice(db_session, company)

    detail_before = client.get(f"/api/ihm/invoices/{invoice.id}").json()
    assert detail_before["last_download_at"] is None
    assert detail_before["last_download_by"] is None

    client.get(f"/api/ihm/invoices/{invoice.id}/download")

    detail_after = client.get(f"/api/ihm/invoices/{invoice.id}").json()
    assert detail_after["last_download_at"] is not None
    # Toujours pas d'utilisateur identifiable en mode disabled.
    assert detail_after["last_download_by"] is None


def test_download_missing_invoice_returns_404(client, db_session):
    response = client.get("/api/ihm/invoices/999999/download")
    assert response.status_code == 404


def test_download_records_ip_address(client, db_session):
    company_id = _make_company(client)
    company = db_session.get(Company, company_id)
    invoice = _make_invoice(db_session, company)

    client.get(f"/api/ihm/invoices/{invoice.id}/download")

    log = db_session.query(AuditLog).filter(AuditLog.action == "invoice_download").one()
    assert log.ip_address is not None
