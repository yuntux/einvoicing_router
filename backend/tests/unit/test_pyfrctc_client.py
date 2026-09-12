"""PyfrctcSuperPDPClient — mapping pyfrctc -> RawInvoice (spec.md § 4.1/NF7, lot 6),
avec une session mockée (aucun réseau)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from app.afnor.client.pyfrctc_client import PyfrctcSuperPDPClient


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
    <ram:TypeCode>380</ram:TypeCode>
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


def test_fetch_received_invoices_maps_flow_to_raw_invoice():
    """Le Metadata du flux (schéma officiel "AFNOR Flow Service") ne porte que
    l'enveloppe de transport (flowSyntax, processingRule, name...) — jamais les
    champs métier de la facture (émetteur, montants, numéro), qui doivent être
    extraits du fichier facture lui-même (docType=Original, ici un CII)."""
    session = MagicMock()
    flow = {"flowId": "flow-1", "submitted_at": datetime(2026, 1, 1, 10, 0)}
    metadata = {
        "flowId": "flow-1",
        "flowSyntax": "CII",
        "processingRule": "B2B",
        "processingRuleSource": "Computed",
        "flowProfile": "Basic",
        "name": "facture.xml",
        "trackingId": "trk-1",
        "flowDirection": "In",
        "flow_direction": "in",
        "flowType": "SupplierInvoice",
        "state": "done",
    }

    with (
        patch("app.afnor.client.pyfrctc_client.core.search_flows_parsed", return_value=[flow]) as search,
        patch(
            "app.afnor.client.pyfrctc_client.core.get_flow_metadata_parsed", return_value=metadata
        ) as get_metadata,
        patch("app.afnor.client.pyfrctc_client.core.get_flow", return_value=_CII_SAMPLE) as get_flow,
    ):
        client = PyfrctcSuperPDPClient(session)
        invoices = client.fetch_received_invoices(company_siren="123456789")

    search.assert_called_once()
    get_metadata.assert_called_once_with(session, "flow-1")
    get_flow.assert_called_once_with(session, "flow-1", doc_type="Original")

    assert len(invoices) == 1
    invoice = invoices[0]
    assert invoice.superpdp_flow_id == "flow-1"
    assert invoice.invoice_number == "F-2026-01"
    assert invoice.emitter_siren == "123456789"
    assert invoice.emitter_name == "Fournisseur Test SAS"
    assert invoice.amount_total == 1200.0
    assert invoice.amount_excl_tax == 1000.0
    assert invoice.currency == "EUR"
    assert invoice.syntax == "CII"
    assert invoice.file_content == _CII_SAMPLE
    assert invoice.flow_profile == "Basic"
    assert invoice.processing_rule_source == "Computed"
    assert invoice.tracking_id == "trk-1"
    assert invoice.flow_direction == "in"
    assert invoice.flow_type == "SupplierInvoice"
    assert invoice.flow_name == "facture.xml"
    assert invoice.ack_status == "done"


def test_fetch_received_invoices_skips_flow_without_id():
    session = MagicMock()
    with patch("app.afnor.client.pyfrctc_client.core.search_flows_parsed", return_value=[{}]):
        client = PyfrctcSuperPDPClient(session)
        invoices = client.fetch_received_invoices(company_siren="123456789")
    assert invoices == []


def test_fetch_received_invoices_empty_when_no_flows():
    session = MagicMock()
    with patch("app.afnor.client.pyfrctc_client.core.search_flows_parsed", return_value=[]):
        client = PyfrctcSuperPDPClient(session)
        invoices = client.fetch_received_invoices(company_siren="123456789")
    assert invoices == []
