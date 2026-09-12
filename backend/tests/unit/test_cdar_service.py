"""cdar_service — génération CDAR réelle validée XSD (spec.md § 4.2/NF7, lot 6).

Aucun réseau requis : `check_xsd=True` valide localement contre le XSD officiel
embarqué dans pyfrctc, `check_schematron` reste désactivé par défaut
(`settings.saxon_server_url` non configuré)."""

from datetime import date

from app.models.invoicing import Invoice
from app.models.lifecycle import LifecycleEventPayment
from app.models.referential import Company
from app.services import cdar_service


def _invoice():
    return Invoice(
        id=1,
        company_id=1,
        emitter_siren="987654321",
        emitter_siret=None,
        invoice_number="F-2026-01",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/x.pdf",
        certified_platform_flow_id="flow-abc",
    )


def _company():
    return Company(id=1, siren="123456789", name="Acheteur SAS")


def test_generate_dispute_with_reason_is_xsd_valid():
    data_dict = cdar_service.build_data_dict(
        invoice=_invoice(),
        buyer_company=_company(),
        status="dispute",
        reason="TX_TVA_ERR",
        action="NIN",
        comment="Le taux appliqué est incorrect.",
    )
    xml_bytes = cdar_service.generate(data_dict)
    assert b"CrossDomainAcknowledgementAndResponse" in xml_bytes
    assert b"207" in xml_bytes  # cdar_code de "dispute"


def test_generate_approved_without_detail_is_xsd_valid():
    data_dict = cdar_service.build_data_dict(
        invoice=_invoice(), buyer_company=_company(), status="approved"
    )
    xml_bytes = cdar_service.generate(data_dict)
    assert b"205" in xml_bytes


def test_generate_payment_sent_with_payment_lines_is_xsd_valid():
    payments = [LifecycleEventPayment(amount=123.45, currency="EUR", payment_date=date(2026, 1, 5))]
    data_dict = cdar_service.build_data_dict(
        invoice=_invoice(), buyer_company=_company(), status="payment_sent", payments=payments
    )
    xml_bytes = cdar_service.generate(data_dict)
    assert b"211" in xml_bytes


def test_to_json_safe_serializes_dates():
    data_dict = cdar_service.build_data_dict(
        invoice=_invoice(), buyer_company=_company(), status="approved"
    )
    safe = cdar_service.to_json_safe(data_dict)
    import json

    json.dumps(safe)  # ne doit pas lever
    assert isinstance(safe["MDT-8"], str)
    assert isinstance(safe["MDT-100"], str)
