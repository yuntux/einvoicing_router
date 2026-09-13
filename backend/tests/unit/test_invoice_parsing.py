"""app.afnor.invoice_parsing — extraction des champs métier depuis le fichier
facture lui-même (CII/Factur-X, UBL), le Metadata du flux AFNOR n'en portant
aucun (cf. schéma officiel "AFNOR Flow Service", § 4.1)."""

from datetime import date

from app.afnor.invoice_parsing import invoice_type_from_code, parse_invoice_fields

_CII_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
  xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
  xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocumentContext>
    <ram:GuidelineSpecifiedDocumentContextParameter>
      <ram:ID>urn:cen.eu:en16931:2017</ram:ID>
    </ram:GuidelineSpecifiedDocumentContextParameter>
  </rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument>
    <ram:ID>F-2026-01</ram:ID>
    <ram:TypeCode>381</ram:TypeCode>
    <ram:IssueDateTime>
      <udt:DateTimeString format="102">20260102</udt:DateTimeString>
    </ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
    <ram:ApplicableHeaderTradeAgreement>
      <ram:SellerTradeParty>
        <ram:GlobalID schemeID="0002">123456789</ram:GlobalID>
        <ram:Name>Fournisseur Test SAS</ram:Name>
        <ram:PostalTradeAddress><ram:CountryID>FR</ram:CountryID></ram:PostalTradeAddress>
      </ram:SellerTradeParty>
      <ram:BuyerTradeParty>
        <ram:Name>Client Test</ram:Name>
        <ram:PostalTradeAddress><ram:CountryID>FR</ram:CountryID></ram:PostalTradeAddress>
      </ram:BuyerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeDelivery/>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:LineTotalAmount>1000.00</ram:LineTotalAmount>
        <ram:TaxBasisTotalAmount>1000.00</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">200.00</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>1200.00</ram:GrandTotalAmount>
        <ram:DuePayableAmount>1200.00</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""

_UBL_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2">
  <cbc:ID>U-2026-01</cbc:ID>
  <cbc:IssueDate>2026-01-02</cbc:IssueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>Fournisseur UBL SAS</cbc:RegistrationName>
        <cbc:CompanyID>12345678900012</cbc:CompanyID>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:TaxTotal>
    <cbc:TaxAmount>100.00</cbc:TaxAmount>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:TaxExclusiveAmount>500.00</cbc:TaxExclusiveAmount>
    <cbc:PayableAmount>600.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</Invoice>"""


def test_parse_cii_extracts_business_fields():
    fields = parse_invoice_fields(_CII_SAMPLE, "CII")

    assert fields.emitter_siren == "123456789"
    assert fields.emitter_siret is None
    assert fields.emitter_name == "Fournisseur Test SAS"
    assert fields.invoice_number == "F-2026-01"
    assert fields.invoice_date == date(2026, 1, 2)
    assert fields.amount_total == 1200.0
    assert fields.amount_excl_tax == 1000.0
    # Déclaré tel quel (ram:TaxTotalAmount), jamais recalculé par soustraction — sur
    # cet échantillon ça coïnciderait de toute façon, la vraie garantie est vérifiée
    # par le test dédié `test_amount_tax_is_not_recomputed_by_subtraction`.
    assert fields.amount_tax == 200.0
    assert fields.currency == "EUR"
    assert fields.type_code == "381"


_CII_SAMPLE_LEGAL_ORGANIZATION_ONLY = b"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
  xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
  xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocumentContext>
    <ram:GuidelineSpecifiedDocumentContextParameter>
      <ram:ID>urn:cen.eu:en16931:2017</ram:ID>
    </ram:GuidelineSpecifiedDocumentContextParameter>
  </rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument>
    <ram:ID>F-2026-02</ram:ID>
    <ram:TypeCode>380</ram:TypeCode>
    <ram:IssueDateTime>
      <udt:DateTimeString format="102">20260102</udt:DateTimeString>
    </ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
    <ram:ApplicableHeaderTradeAgreement>
      <ram:SellerTradeParty>
        <ram:Name>Fournisseur Sans GlobalID SAS</ram:Name>
        <ram:SpecifiedLegalOrganization>
          <ram:ID schemeID="0002">987654321</ram:ID>
        </ram:SpecifiedLegalOrganization>
        <ram:PostalTradeAddress><ram:CountryID>FR</ram:CountryID></ram:PostalTradeAddress>
      </ram:SellerTradeParty>
      <ram:BuyerTradeParty>
        <ram:Name>Client Test</ram:Name>
        <ram:PostalTradeAddress><ram:CountryID>FR</ram:CountryID></ram:PostalTradeAddress>
      </ram:BuyerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeDelivery/>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:LineTotalAmount>1000.00</ram:LineTotalAmount>
        <ram:TaxBasisTotalAmount>1000.00</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">200.00</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>1200.00</ram:GrandTotalAmount>
        <ram:DuePayableAmount>1200.00</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""


def test_parse_cii_falls_back_to_legal_organization_id_without_global_id():
    """Régression : un émetteur sans `ram:GlobalID` (mais avec `ram:Specified
    LegalOrganization/ram:ID`, cf. facture réelle `F20260913_011610_752`) donnait un
    SIREN vide — la norme n'impose pas laquelle des deux localisations un émetteur
    doit renseigner. Un SIREN vide fait ensuite échouer l'émission de CDAR
    (BR-FR-CDV-13/MDT-129, "l'identifiant du vendeur... est obligatoire")."""
    fields = parse_invoice_fields(_CII_SAMPLE_LEGAL_ORGANIZATION_ONLY, "CII")
    assert fields.emitter_siren == "987654321"
    assert fields.emitter_name == "Fournisseur Sans GlobalID SAS"


def _build_facturx_pdf(cii_xml: bytes) -> bytes:
    """Un flux `flowSyntax=Factur-X` est un PDF/A-3 avec l'XML CII embarqué comme
    pièce jointe (pas du XML brut) — on en construit un vrai pour le test plutôt
    que de supposer que `parse_facturx` reçoit du XML directement."""
    from io import BytesIO

    from drafthorse.pdf import attach_xml
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return attach_xml(buf.getvalue(), cii_xml, level="BASIC")


def test_parse_facturx_extracts_xml_embedded_in_pdf():
    facturx_pdf = _build_facturx_pdf(_CII_SAMPLE)

    fields = parse_invoice_fields(facturx_pdf, "Factur-X")

    assert fields.emitter_name == "Fournisseur Test SAS"
    assert fields.emitter_siren == "123456789"
    assert fields.invoice_number == "F-2026-01"
    assert fields.amount_total == 1200.0


def test_parse_facturx_returns_empty_when_given_raw_xml_not_pdf():
    """Un flux Factur-X est toujours un PDF — du XML brut (mauvais flowSyntax,
    métadonnée erronée...) ne doit jamais planter tout le cycle d'ingestion."""
    fields = parse_invoice_fields(_CII_SAMPLE, "Factur-X")
    assert fields.emitter_name is None


def test_parse_ubl_extracts_business_fields():
    fields = parse_invoice_fields(_UBL_SAMPLE, "UBL")

    assert fields.emitter_siren == "123456789"
    assert fields.emitter_siret == "12345678900012"
    assert fields.emitter_name == "Fournisseur UBL SAS"
    assert fields.invoice_number == "U-2026-01"
    assert fields.invoice_date == date(2026, 1, 2)
    assert fields.amount_total == 600.0
    assert fields.amount_excl_tax == 500.0
    assert fields.amount_tax == 100.0
    assert fields.currency == "EUR"
    assert fields.type_code == "380"


def test_amount_tax_is_not_recomputed_by_subtraction():
    """Régression : `amount_tax` doit provenir du champ déclaré dans le fichier, pas
    d'une soustraction `amount_total - amount_excl_tax` — celle-ci accumule des
    erreurs de représentation flottante (ex. 303.3299999999999) et peut être fausse
    dès qu'un arrondi ou un acompte intervient dans le fichier d'origine. Ce fixture
    déclare volontairement un `TaxAmount` qui NE correspond PAS à la soustraction
    (600 - 500 = 100, mais le fichier déclare 99.99) pour prouver que la valeur
    utilisée est bien celle du fichier."""
    xml = _UBL_SAMPLE.replace(b"<cbc:TaxAmount>100.00</cbc:TaxAmount>", b"<cbc:TaxAmount>99.99</cbc:TaxAmount>")
    fields = parse_invoice_fields(xml, "UBL")
    assert fields.amount_tax == 99.99


def test_parse_invoice_fields_returns_empty_on_unknown_syntax():
    fields = parse_invoice_fields(b"not-xml", "CDAR")
    assert fields.emitter_name is None
    assert fields.invoice_number is None


def test_parse_invoice_fields_returns_empty_on_malformed_content():
    fields = parse_invoice_fields(b"not-xml-at-all", "CII")
    assert fields.emitter_name is None
    assert fields.invoice_number is None


def test_invoice_type_from_code():
    assert invoice_type_from_code("381") == "credit_note"
    assert invoice_type_from_code("380") == "invoice"
    assert invoice_type_from_code(None) == "invoice"


def test_parse_ubl_does_not_resolve_external_entities():
    """Garde-fou XXE (CWE-611) : une facture UBL reçue d'un fournisseur tiers, pas
    nécessairement de confiance, ne doit jamais pouvoir faire lire un fichier local
    du serveur via une entité externe déclarée dans son DOCTYPE."""
    xxe_payload = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Invoice [<!ENTITY xxe SYSTEM "file:///etc/hostname">]>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2">
  <cbc:ID>&xxe;</cbc:ID>
</Invoice>"""

    fields = parse_invoice_fields(xxe_payload, "UBL")

    # L'entité externe n'est jamais résolue : le DOCTYPE fait rejeter le document
    # (`parse_invoice_fields` avale l'exception et retourne des champs vides) plutôt
    # que de substituer `&xxe;` par le contenu du fichier système ciblé.
    assert fields.invoice_number is None
