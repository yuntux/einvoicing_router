"""lifecycle_ingestion_service — rattachement des CDAR entrants (§ 4.2) à la facture
existante correspondante pendant le cycle de polling (jamais une nouvelle `Invoice`,
cf. l'incident du flux ie_78332)."""

from datetime import date

from app.afnor.client.base import RawIncomingCdar
from app.afnor.client.fake import FakeCertifiedPlatformClient
from app.models.invoicing import Invoice
from app.models.referential import Company
from app.services import cdar_service
from app.services.lifecycle_ingestion_service import ingest_incoming_lifecycle_events


def _make_company_and_invoice(db, *, siren="555555555", invoice_number="F-001"):
    company = Company(siren=siren, name="Ma Société")
    db.add(company)
    db.commit()
    db.refresh(company)

    invoice = Invoice(
        company_id=company.id,
        emitter_siren="666666666",
        invoice_number=invoice_number,
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/fake.pdf",
        certified_platform_flow_id="flow-abc",
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return company, invoice


def _cdar_bytes(invoice, *, status="approved", **kwargs) -> bytes:
    data_dict = cdar_service.build_data_dict(
        invoice=invoice, buyer_company=invoice.company, status=status, **kwargs
    )
    return cdar_service.generate(data_dict)


def test_ingest_matches_by_invoice_number(db_session):
    company, invoice = _make_company_and_invoice(db_session)
    xml_bytes = _cdar_bytes(invoice, status="dispute", reason="TX_TVA_ERR")
    client = FakeCertifiedPlatformClient(
        incoming_cdars=[RawIncomingCdar(flow_id="cdar-1", xml_bytes=xml_bytes)]
    )

    result = ingest_incoming_lifecycle_events(db_session, company=company, client=client)

    assert len(result.created) == 1
    assert result.created[0].status == "dispute"
    assert result.unmatched_flow_ids == []
    assert result.failed_flow_ids == []
    db_session.refresh(invoice)
    assert invoice.lifecycle_status == "dispute"


def test_ingest_reports_unmatched_invoice_number(db_session):
    company, invoice = _make_company_and_invoice(db_session)
    # CDAR référençant une facture qui n'existe pas encore chez nous (reçu avant la
    # facture elle-même, ou hors périmètre) — ne doit jamais planter le cycle. Un
    # objet transitoire (jamais ajouté à la session) suffit : `build_data_dict` ne lit
    # que ses attributs, sans requête DB.
    ghost_invoice = Invoice(
        company_id=invoice.company_id,
        emitter_siren=invoice.emitter_siren,
        invoice_number="F-GHOST",
        invoice_date=invoice.invoice_date,
        file_path=invoice.file_path,
        certified_platform_flow_id="flow-ghost",
    )
    data_dict = cdar_service.build_data_dict(invoice=ghost_invoice, buyer_company=company, status="approved")
    xml_bytes = cdar_service.generate(data_dict)
    client = FakeCertifiedPlatformClient(
        incoming_cdars=[RawIncomingCdar(flow_id="cdar-2", xml_bytes=xml_bytes)]
    )

    result = ingest_incoming_lifecycle_events(db_session, company=company, client=client)

    assert result.created == []
    assert result.unmatched_flow_ids == ["cdar-2"]
    assert result.failed_flow_ids == []


def test_ingest_does_not_match_across_companies(db_session):
    company_a, invoice_a = _make_company_and_invoice(db_session, siren="111111111", invoice_number="F-SAME")
    company_b, invoice_b = _make_company_and_invoice(db_session, siren="222222222", invoice_number="F-SAME")
    xml_bytes = _cdar_bytes(invoice_a, status="approved")
    # Même numéro de facture chez les deux entreprises, mais le CDAR arrive pour
    # l'entreprise B : il doit se rattacher à SA facture (scoping par company_id),
    # jamais à celle de l'entreprise A.
    client = FakeCertifiedPlatformClient(
        incoming_cdars=[RawIncomingCdar(flow_id="cdar-3", xml_bytes=xml_bytes)]
    )

    result = ingest_incoming_lifecycle_events(db_session, company=company_b, client=client)

    assert len(result.created) == 1
    assert result.created[0].invoice_id == invoice_b.id
    assert result.created[0].invoice_id != invoice_a.id
    assert result.unmatched_flow_ids == []


def test_ingest_reports_unparsable_cdar_as_failed(db_session):
    company, _invoice = _make_company_and_invoice(db_session)
    client = FakeCertifiedPlatformClient(
        incoming_cdars=[RawIncomingCdar(flow_id="cdar-bad", xml_bytes=b"<not-xml>")]
    )

    result = ingest_incoming_lifecycle_events(db_session, company=company, client=client)

    assert result.created == []
    assert result.failed_flow_ids == ["cdar-bad"]
