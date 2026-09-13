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


def test_generated_cdar_satisfies_superpdp_business_rules_not_covered_by_local_xsd():
    """`check_xsd=True` valide la structure XML contre le XSD officiel, mais pas les
    règles métier (schématron `BR-FR-CDV-*`) que seul SuperPDP applique réellement
    (`check_schematron` exige un serveur Saxon, absent en test/CI). Ces trois valeurs
    ont été mal choisies à l'origine (recopiées des constantes facture, pas CDAR) et
    faisaient échouer TOUT envoi de CDAR contre le vrai bac à sable, quels que soient
    les identifiants d'entreprise (cf. BR-FR-CDV-02/09/CL-01 renvoyés par SuperPDP) —
    on épingle ici les valeurs correctes en l'absence de validation schématron locale."""
    data_dict = cdar_service.build_data_dict(
        invoice=_invoice(), buyer_company=_company(), status="suspended", reason="SIRET_ERR"
    )
    # BR-FR-CDV-02/MDT-3 : guideline CDV, pas la guideline Factur-X d'une facture.
    assert data_dict["MDT-3"] == "urn.cpro.gouv.fr:1p0:CDV:invoice"
    # BR-FR-CDV-CL-01/MDT-2 : liste fermée hors PPF (REGULATED/NON_REGULATED/B2C/...).
    assert data_dict["MDT-2"] == "REGULATED"
    # BR-FR-CDV-09/MDT-77 : "23" ou "305" seulement — "305" exige un rôle MDT-21/
    # MDT-40 = "WK" (BR-FR-CDV-CL-02/03) qu'on n'utilise jamais (toujours "BY"/"SE").
    assert data_dict["MDT-77"] == "23"
    assert data_dict["MDT-21"] == "BY"
    assert data_dict["MDT-40"] == "SE"


def test_build_data_dict_uses_certified_platform_directory_id_when_set():
    """`MDT-57` (identifiant acheteur/destinataire) doit utiliser l'identifiant
    annuaire de la plateforme certifiée quand il est renseigné — un bac à sable AFNOR
    peut immatriculer l'entreprise sous un identifiant technique différent du SIREN
    légal (§ cf. Company.certified_platform_directory_id), auquel cas envoyer le
    SIREN légal fait échouer la résolution de l'entreprise côté annuaire."""
    company = _company()
    company.certified_platform_directory_id = "000000001"
    data_dict = cdar_service.build_data_dict(invoice=_invoice(), buyer_company=company, status="approved")
    assert data_dict["MDT-57"] == {"0002": "000000001"}


def test_build_data_dict_mdt129_is_the_original_invoice_issuer_not_the_buyer():
    """MDT-129 (`ram:ReferenceReferencedDocument/ram:IssuerTradeParty`) : `pyfrctc`
    le mappe explicitement sur la clé "invoice_issuer" en lecture
    (`parse_cdar_from_raw`) — c'est l'émetteur de la facture D'ORIGINE référencée
    (le fournisseur), jamais l'acheteur qui accuse réception. Y mettre
    l'identifiant acheteur empêchait SuperPDP de retrouver la facture référencée
    ("no matching invoices found", corrélation faite sur MDT-87 + MDT-129)."""
    company = _company()
    company.certified_platform_directory_id = "000000001"
    data_dict = cdar_service.build_data_dict(invoice=_invoice(), buyer_company=company, status="approved")
    assert data_dict["MDT-129"] == {"0002": "987654321"}
    assert data_dict["MDT-129"] == data_dict["MDT-38"]


def test_build_data_dict_falls_back_to_siren_without_directory_id():
    data_dict = cdar_service.build_data_dict(invoice=_invoice(), buyer_company=_company(), status="approved")
    assert data_dict["MDT-57"] == {"0002": "123456789"}


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
