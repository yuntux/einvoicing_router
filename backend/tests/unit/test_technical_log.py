"""TechnicalLog — résultat métier du polling (§ 6.1, lot 8) + purge selon
RouterSettings.technical_log_retention_days."""

from datetime import date, datetime, timedelta

from app.afnor.client.base import RawInvoice
from app.afnor.client.fake import FakeCertifiedPlatformClient
from app.models.audit import TechnicalLog
from app.models.referential import Company
from app.scheduler.polling_job import run_polling_cycle
from app.services import router_settings_service
from app.services.technical_log_purge_service import purge_technical_logs


def _make_company(db, siren="123456789"):
    company = Company(siren=siren, name="Ma Société")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def test_polling_cycle_records_success_technical_log(db_session, monkeypatch):
    company = _make_company(db_session)
    raw = RawInvoice(
        certified_platform_flow_id="flow-1",
        emitter_siren="987654321",
        invoice_number="F-1",
        invoice_date=date(2026, 1, 1),
        file_name="F-1.pdf",
        file_content=b"%PDF-fake",
    )
    monkeypatch.setattr(
        "app.scheduler.polling_job.resolve_client_for_company",
        lambda db, company: FakeCertifiedPlatformClient([raw]),
    )

    run_polling_cycle(db_session)

    logs = db_session.query(TechnicalLog).filter(TechnicalLog.company_id == company.id).all()
    assert len(logs) == 1
    assert logs[0].log_type == "invoice_polling"
    assert logs[0].new_count == 1
    assert logs[0].updated_count == 0
    # Pas de règle de routage pour cet émetteur -> facture non routée -> "warning".
    assert logs[0].status == "warning"


def test_polling_cycle_sets_last_polled_at_and_passes_it_as_since(db_session, monkeypatch):
    """§ 4.1/lot 9 : le curseur `Company.last_polled_at` doit être posé après un cycle
    réussi et transmis comme `since` au cycle suivant, pour ne plus re-scanner tout
    l'historique à chaque déclenchement du scheduler."""
    company = _make_company(db_session)
    assert company.last_polled_at is None

    received_since: list[object] = []

    class RecordingClient:
        def fetch_received_invoices(self, *, company_siren, since=None):
            received_since.append(since)
            return []

    monkeypatch.setattr(
        "app.scheduler.polling_job.resolve_client_for_company",
        lambda db, company: RecordingClient(),
    )

    run_polling_cycle(db_session)
    db_session.refresh(company)
    first_cursor = company.last_polled_at
    assert first_cursor is not None
    assert received_since == [None]

    run_polling_cycle(db_session)
    db_session.refresh(company)

    assert received_since == [None, first_cursor]
    assert company.last_polled_at >= first_cursor


def test_polling_cycle_records_error_technical_log_on_client_failure(db_session, monkeypatch):
    _make_company(db_session)

    class FailingClient:
        def fetch_received_invoices(self, *, company_siren, since=None):
            raise RuntimeError("SuperPDP unreachable")

    monkeypatch.setattr(
        "app.scheduler.polling_job.resolve_client_for_company", lambda db, company: FailingClient()
    )

    run_polling_cycle(db_session)

    logs = db_session.query(TechnicalLog).all()
    assert len(logs) == 1
    assert logs[0].status == "error"
    assert "SuperPDP unreachable" in logs[0].details


def test_polling_cycle_survives_client_resolution_failure_for_one_company(db_session, monkeypatch):
    """`resolve_client_for_company` peut lever (ex. aucun identifiant SuperPDP
    configuré, § 4.10) tout comme `fetch_received_invoices` — les deux doivent être
    couverts par le même filet, sans quoi une seule entreprise mal configurée
    empêche le polling de toutes les autres (et ne laisse même pas de trace dans
    `TechnicalLog` pour elle-même)."""
    unconfigured = _make_company(db_session, siren="111111112")
    configured = _make_company(db_session, siren="222222223")

    def fake_resolve(db, company):
        if company.id == unconfigured.id:
            raise ValueError("Aucun identifiant SuperPDP configuré")
        return FakeCertifiedPlatformClient([])

    monkeypatch.setattr("app.scheduler.polling_job.resolve_client_for_company", fake_resolve)

    run_polling_cycle(db_session)

    logs = {log.company_id: log for log in db_session.query(TechnicalLog).all()}
    assert logs[unconfigured.id].status == "error"
    assert "SuperPDP" in logs[unconfigured.id].details
    assert logs[configured.id].status == "success"


def test_purge_technical_logs_respects_retention(db_session):
    router_settings_service.update_settings(db_session, technical_log_retention_days=30)

    old_log = TechnicalLog(
        log_type="invoice_polling",
        origin="scheduler",
        status="success",
        created_at=datetime.utcnow() - timedelta(days=60),
    )
    recent_log = TechnicalLog(
        log_type="invoice_polling",
        origin="scheduler",
        status="success",
        created_at=datetime.utcnow() - timedelta(days=5),
    )
    db_session.add_all([old_log, recent_log])
    db_session.commit()

    deleted = purge_technical_logs(db_session)

    assert deleted == 1
    remaining = db_session.query(TechnicalLog).all()
    assert len(remaining) == 1
    assert remaining[0].id == recent_log.id


def test_purge_technical_logs_uses_configured_retention_days(db_session):
    router_settings_service.update_settings(db_session, technical_log_retention_days=1)

    log = TechnicalLog(
        log_type="invoice_polling",
        origin="scheduler",
        status="success",
        created_at=datetime.utcnow() - timedelta(days=2),
    )
    db_session.add(log)
    db_session.commit()

    deleted = purge_technical_logs(db_session)
    assert deleted == 1
