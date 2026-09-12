"""AfnorClientAdapter — capture et rédaction des en-têtes HTTP bruts dans FlowTrace
(spec.md § NF1), sans réseau (session/`core` pyfrctc mockés)."""

from types import SimpleNamespace
from unittest.mock import patch

from app.afnor.client.adapter import AfnorClientAdapter
from app.models.audit import FlowTrace
from app.models.referential import Company


def _make_company(db, siren="123456782"):
    company = Company(siren=siren, name="Ma Société")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


class _FakeResponse:
    def __init__(self, request_headers: dict, response_headers: dict):
        self.request = SimpleNamespace(headers=request_headers)
        self.headers = response_headers


def _fake_session_firing(request_headers: dict, response_headers: dict):
    """Session factice dont `.hooks["response"]` se comporte comme une vraie session
    `requests` : `_fire()` simule l'appel du hook après une requête HTTP."""
    session = SimpleNamespace(hooks={"response": []})

    def _fire():
        response = _FakeResponse(request_headers, response_headers)
        for hook in list(session.hooks["response"]):
            hook(response)

    session._fire = _fire
    return session


def test_lookup_directory_siren_captures_and_redacts_headers(db_session):
    company = _make_company(db_session)
    session = _fake_session_firing(
        request_headers={"Authorization": "Bearer secret-token", "Accept": "application/json"},
        response_headers={"Content-Type": "application/json", "Set-Cookie": "sid=abc"},
    )

    def fake_get_directory_siren_parsed(session, siren):
        session._fire()
        return {"siren": siren, "name": "ACME"}

    adapter = AfnorClientAdapter()
    with (
        patch.object(adapter, "_get_or_build_session", return_value=session),
        patch(
            "app.afnor.client.adapter.core.get_directory_siren_parsed",
            side_effect=fake_get_directory_siren_parsed,
        ),
    ):
        result = adapter.lookup_directory_siren(db_session, company=company, siren="123456782")

    assert result == {"siren": "123456782", "name": "ACME"}

    trace = db_session.query(FlowTrace).one()
    assert trace.request_headers == {
        "Authorization": "***REDACTED***",
        "Accept": "application/json",
    }
    assert trace.response_headers == {
        "Content-Type": "application/json",
        "Set-Cookie": "***REDACTED***",
    }
    # Le hook temporaire est retiré après l'appel, pas accumulé d'un appel à l'autre.
    assert session.hooks["response"] == []


def test_send_invoice_captures_headers_on_success(db_session):
    company = _make_company(db_session)
    session = _fake_session_firing(
        request_headers={"Authorization": "Bearer secret-token"},
        response_headers={"Content-Type": "application/json"},
    )

    def fake_send_flow_parsed(session, file_bin, filename, flow_syntax, processing_rule):
        session._fire()
        return {"id": "flow-1", "state": "sent"}

    adapter = AfnorClientAdapter()
    with (
        patch.object(adapter, "_get_or_build_session", return_value=session),
        patch(
            "app.afnor.client.adapter.core.send_flow_parsed", side_effect=fake_send_flow_parsed
        ),
    ):
        result = adapter.send_invoice(
            db_session,
            company=company,
            file_bin=b"<invoice/>",
            filename="invoice.xml",
            flow_syntax="Factur-X",
            processing_rule="B2B",
        )

    assert result == {"id": "flow-1", "state": "sent"}
    trace = db_session.query(FlowTrace).one()
    assert trace.request_headers == {"Authorization": "***REDACTED***"}
    assert trace.response_headers == {"Content-Type": "application/json"}


def test_send_invoice_captures_headers_on_failure(db_session):
    company = _make_company(db_session)
    session = _fake_session_firing(
        request_headers={"Authorization": "Bearer secret-token"},
        response_headers={"Content-Type": "application/json"},
    )

    def fake_send_flow_parsed(session, file_bin, filename, flow_syntax, processing_rule):
        session._fire()
        raise RuntimeError("SuperPDP unreachable")

    adapter = AfnorClientAdapter()
    with (
        patch.object(adapter, "_get_or_build_session", return_value=session),
        patch(
            "app.afnor.client.adapter.core.send_flow_parsed", side_effect=fake_send_flow_parsed
        ),
    ):
        try:
            adapter.send_invoice(
                db_session,
                company=company,
                file_bin=b"<invoice/>",
                filename="invoice.xml",
                flow_syntax="Factur-X",
                processing_rule="B2B",
            )
        except RuntimeError:
            pass

    trace = db_session.query(FlowTrace).one()
    assert trace.http_status == 502
    assert trace.request_headers == {"Authorization": "***REDACTED***"}
    assert trace.response_headers == {"Content-Type": "application/json"}


def test_no_headers_captured_when_session_never_fires(db_session):
    """Si aucun appel HTTP n'a lieu (ex. réponse déjà en cache), les colonnes headers
    restent `None` plutôt que de fausses valeurs."""
    company = _make_company(db_session)
    session = _fake_session_firing(request_headers={}, response_headers={})
    adapter = AfnorClientAdapter()

    with (
        patch.object(adapter, "_get_or_build_session", return_value=session),
        patch(
            "app.afnor.client.adapter.core.get_directory_siren_parsed",
            return_value={"siren": "123456782"},
        ),
    ):
        result = adapter.lookup_directory_siren(db_session, company=company, siren="123456782")

    assert result == {"siren": "123456782"}
    trace = db_session.query(FlowTrace).one()
    assert trace.request_headers is None
    assert trace.response_headers is None
