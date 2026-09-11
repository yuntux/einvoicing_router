"""PyfrctcSuperPDPClient — mapping pyfrctc -> RawInvoice (spec.md § 4.1/NF7, lot 6),
avec une session mockée (aucun réseau)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from app.afnor.client.pyfrctc_client import PyfrctcSuperPDPClient


def test_fetch_received_invoices_maps_flow_to_raw_invoice():
    session = MagicMock()
    flow = {"id": "flow-1", "submitted_at": datetime(2026, 1, 1, 10, 0)}
    metadata = {
        "invoiceNumber": "F-2026-01",
        "emitterSiren": "123456789",
        "amountTotal": 1200.0,
        "currency": "EUR",
        "invoiceDate": "2026-01-02T00:00:00Z",
    }

    with (
        patch("app.afnor.client.pyfrctc_client.core.search_flows_parsed", return_value=[flow]) as search,
        patch(
            "app.afnor.client.pyfrctc_client.core.get_flow_metadata_parsed", return_value=metadata
        ) as get_metadata,
        patch("app.afnor.client.pyfrctc_client.core.get_flow", return_value=b"%PDF-fake") as get_flow,
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
    assert invoice.amount_total == 1200.0
    assert invoice.file_content == b"%PDF-fake"


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
