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


def test_build_data_dict_uses_certified_platform_directory_id_when_set():
    """`MDT-57`/`MDT-129` (identifiant acheteur) doivent utiliser l'identifiant
    annuaire de la plateforme certifiée quand il est renseigné — un bac à sable AFNOR
    peut immatriculer l'entreprise sous un identifiant technique différent du SIREN
    légal (§ cf. Company.certified_platform_directory_id), auquel cas envoyer le
    SIREN légal fait échouer la résolution de l'entreprise côté annuaire."""
    company = _company()
    company.certified_platform_directory_id = "000000001"
    data_dict = cdar_service.build_data_dict(invoice=_invoice(), buyer_company=company, status="approved")
    assert data_dict["MDT-57"] == {"0002": "000000001"}
    assert data_dict["MDT-129"] == {"0002": "000000001"}


def test_build_data_dict_falls_back_to_siren_without_directory_id():
    data_dict = cdar_service.build_data_dict(invoice=_invoice(), buyer_company=_company(), status="approved")
    assert data_dict["MDT-57"] == {"0002": "123456789"}
    assert data_dict["MDT-129"] == {"0002": "123456789"}


def test_build_data_dict_mdt87_is_invoice_number_not_flow_id():
    """MDT-87 (IssuerAssignedID) doit porter le numéro de facture métier — c'est ce
    que la contrepartie connaît et peut rapprocher de sa propre facture, jamais notre
    identifiant technique de flux AFNOR (cf. `l10n_fr_einvoicing`, qui y met
    `invoice.ref`/`invoice.name`)."""
    invoice = _invoice()
    data_dict = cdar_service.build_data_dict(invoice=invoice, buyer_company=_company(), status="approved")
    assert data_dict["MDT-87"] == invoice.invoice_number
    assert data_dict["MDT-87"] != invoice.certified_platform_flow_id


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


def test_parse_round_trips_a_generated_cdar():
    """`cdar_service.parse` (entrant, § 4.2) doit relire ce que `build_data_dict` +
    `generate` (sortant) ont produit — notamment `MDT-87`/`invoice_number` (rattachement
    à la facture, cf. `lifecycle_ingestion_service`) et `MDT-105`/`status_code`
    (résolu via `resolve_status_key`)."""
    invoice = _invoice()
    data_dict = cdar_service.build_data_dict(
        invoice=invoice,
        buyer_company=_company(),
        status="dispute",
        reason="TX_TVA_ERR",
        action="NIN",
        comment="Le taux appliqué est incorrect.",
    )
    xml_bytes = cdar_service.generate(data_dict)

    parsed = cdar_service.parse(xml_bytes)

    assert parsed["invoice_number"] == invoice.invoice_number
    assert parsed["status_code"] == "207"
    assert cdar_service.resolve_status_key(parsed["status_code"]) == "dispute"
    assert parsed["doc_status"][0]["reason_code"] == "TX_TVA_ERR"
    assert parsed["doc_status"][0]["action_code"] == "NIN"
    assert parsed["doc_status"][0]["comment"] == "Le taux appliqué est incorrect."


def test_resolve_status_key_unknown_code_returns_none():
    assert cdar_service.resolve_status_key("999999") is None


def test_to_json_safe_serializes_dates():
    data_dict = cdar_service.build_data_dict(
        invoice=_invoice(), buyer_company=_company(), status="approved"
    )
    safe = cdar_service.to_json_safe(data_dict)
    import json

    json.dumps(safe)  # ne doit pas lever
    assert isinstance(safe["MDT-8"], str)
    assert isinstance(safe["MDT-100"], str)
