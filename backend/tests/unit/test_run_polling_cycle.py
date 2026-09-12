"""Relevé manuel des nouvelles factures depuis la page Entreprises (§ 4.1) : force un
passage du cycle de polling sans attendre le prochain déclenchement du scheduler —
même principe que le bouton « Forcer un cycle d'envoi » de la page Échecs de routage
(cf. `test_invoice_routings_api.py`), mais pour le polling plutôt que le retry."""

from datetime import date, datetime

from app.afnor.client.base import RawIncomingCdar, RawInvoice
from app.afnor.client.fake import FakeCertifiedPlatformClient
from app.config import settings
from app.models.audit import TechnicalLog
from app.models.invoicing import Invoice
from app.models.lifecycle import LifecycleEvent
from app.models.referential import Company
from app.scheduler.polling_job import run_polling_cycle
from app.services import cdar_service, client_factory


def test_run_polling_cycle_updates_last_polled_at(client, db_session, monkeypatch):
    # `settings.certified_platform_client_mode` doit valoir "fake" (défaut du code)
    # pour ce test — forcé explicitement car un `.env` de dev présent dans le
    # répertoire d'exécution peut le surcharger (`pydantic-settings` charge `.env`
    # relatif au cwd, indépendamment de pytest).
    monkeypatch.setattr(settings, "certified_platform_client_mode", "fake")
    company = Company(siren="123456782", name="Acme SAS")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    assert company.last_polled_at is None

    response = client.post("/api/ihm/companies/run-polling-cycle")
    assert response.status_code == 204

    db_session.refresh(company)
    assert company.last_polled_at is not None
    assert company.last_polled_at <= datetime.utcnow()


def test_run_polling_cycle_requires_admin(client, monkeypatch):
    """Endpoint monté sur `admin_router` (§ 5.1, page Entreprises) : un utilisateur
    restreint ou lecture seule n'y a pas plus accès qu'aux autres actions de cette
    page (cf. `test_admin_only_pages_scope.py`)."""
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "admin@example.com"}, follow_redirects=False)
    client.post("/api/ihm/users", json={"email": "user@example.com"})
    client.post("/api/ihm/auth/logout")
    client.get("/api/ihm/auth/login", params={"email": "user@example.com"}, follow_redirects=False)

    response = client.post("/api/ihm/companies/run-polling-cycle")
    assert response.status_code == 403


def test_run_polling_cycle_recovers_after_a_company_failure(db_session, monkeypatch):
    """Régression : une exception pendant l'ingestion d'une entreprise (ex. flush SQL
    en échec) laissait la session dans un état "transaction rolled back" — la
    prochaine requête (y compris le `TechnicalLog` d'erreur lui-même) levait alors une
    `PendingRollbackError` qui interrompait tout le cycle, empêchant le polling des
    entreprises suivantes malgré le commentaire du code affirmant le contraire."""
    monkeypatch.setattr(settings, "certified_platform_client_mode", "fake")

    failing_company = Company(siren="111111111", name="Échoue")
    ok_company = Company(siren="222222222", name="OK")
    db_session.add_all([failing_company, ok_company])
    db_session.commit()
    db_session.refresh(failing_company)
    db_session.refresh(ok_company)

    # Une valeur non sérialisable en JSON dans `raw_metadata` fait échouer le flush
    # SQL lors de l'upsert de la facture (`Invoice.afnor_metadata`, colonne JSON) —
    # exactement le scénario observé en production avec les métadonnées `pyfrctc`.
    bad_raw_invoice = RawInvoice(
        certified_platform_flow_id="flow-bad",
        emitter_siren="333333333",
        invoice_number="F-BAD",
        invoice_date=date(2026, 1, 1),
        file_name="bad.pdf",
        file_content=b"%PDF-fake",
        raw_metadata={"submitted_at": datetime(2026, 1, 1)},
    )
    good_raw_invoice = RawInvoice(
        certified_platform_flow_id="flow-good",
        emitter_siren="444444444",
        invoice_number="F-GOOD",
        invoice_date=date(2026, 1, 1),
        file_name="good.pdf",
        file_content=b"%PDF-fake",
    )

    def fake_resolve_client_for_company(db, company):
        if company.id == failing_company.id:
            return FakeCertifiedPlatformClient([bad_raw_invoice])
        return FakeCertifiedPlatformClient([good_raw_invoice])

    monkeypatch.setattr(client_factory, "resolve_client_for_company", fake_resolve_client_for_company)
    monkeypatch.setattr(
        "app.scheduler.polling_job.resolve_client_for_company", fake_resolve_client_for_company
    )

    run_polling_cycle(db_session)

    db_session.refresh(failing_company)
    db_session.refresh(ok_company)
    assert failing_company.last_polled_at is None
    assert ok_company.last_polled_at is not None

    logs = db_session.query(TechnicalLog).order_by(TechnicalLog.id).all()
    statuses_by_company = {log.company_id: log.status for log in logs}
    assert statuses_by_company[failing_company.id] == "error"
    # "warning" plutôt que "success" : aucune règle de routage n'existe pour
    # l'émetteur de test, la facture est donc comptée comme non routée (§ 4.7) — ce
    # qui n'est pas ce que ce test vérifie, seulement que ce second cycle a bien eu
    # lieu malgré l'échec du premier.
    assert statuses_by_company[ok_company.id] == "warning"


def test_run_polling_cycle_ingests_incoming_lifecycle_events(db_session, monkeypatch):
    """Un CDAR entrant (§ 4.2) rencontré pendant le cycle de polling se rattache à la
    facture existante correspondante (par numéro de facture, MDT-87) plutôt que de
    créer une facture fantôme — cf. l'incident du flux ie_78332."""
    monkeypatch.setattr(settings, "certified_platform_client_mode", "fake")

    company = Company(siren="123456782", name="Acme SAS")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    invoice = Invoice(
        company_id=company.id,
        emitter_siren="666666666",
        invoice_number="F-001",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/fake.pdf",
        certified_platform_flow_id="flow-abc",
    )
    db_session.add(invoice)
    db_session.commit()
    db_session.refresh(invoice)

    data_dict = cdar_service.build_data_dict(invoice=invoice, buyer_company=company, status="dispute", reason="TX_TVA_ERR")
    xml_bytes = cdar_service.generate(data_dict)

    def fake_resolve_client_for_company(db, comp):
        return FakeCertifiedPlatformClient(
            incoming_cdars=[RawIncomingCdar(flow_id="cdar-flow-1", xml_bytes=xml_bytes)]
        )

    monkeypatch.setattr(client_factory, "resolve_client_for_company", fake_resolve_client_for_company)
    monkeypatch.setattr(
        "app.scheduler.polling_job.resolve_client_for_company", fake_resolve_client_for_company
    )

    run_polling_cycle(db_session)

    db_session.refresh(invoice)
    assert invoice.lifecycle_status == "dispute"
    events = db_session.query(LifecycleEvent).filter(LifecycleEvent.invoice_id == invoice.id).all()
    assert len(events) == 1
    assert events[0].direction == "in"
    assert events[0].status == "dispute"

    logs = db_session.query(TechnicalLog).filter(TechnicalLog.log_type == "lifecycle_polling").all()
    assert len(logs) == 1
    assert logs[0].status == "success"
    assert logs[0].new_count == 1
