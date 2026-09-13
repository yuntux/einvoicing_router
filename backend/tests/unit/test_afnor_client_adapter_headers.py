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
            "app.afnor.client.adapter.core.get_directory_siren",
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
            "app.afnor.client.adapter.core.send_flow", side_effect=fake_send_flow_parsed
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
            "app.afnor.client.adapter.core.send_flow", side_effect=fake_send_flow_parsed
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


def test_send_invoice_success_response_with_datetime_is_json_safe(db_session):
    """Un résultat contenant un `datetime` natif (ex. si un jour un champ de ce type
    apparaissait dans la réponse brute de `core.send_flow`) ne doit jamais faire
    planter la trace — colonne JSON `FlowTrace.response`. Garde-fou générique,
    indépendant du fait qu'on appelle aujourd'hui `send_flow` (brut) plutôt que
    `send_flow_parsed` (qui, lui, ajoutait volontairement de tels champs)."""
    from datetime import datetime

    company = _make_company(db_session)
    session = _fake_session_firing(request_headers={}, response_headers={})

    def fake_send_flow_parsed(session, file_bin, filename, flow_syntax, processing_rule):
        session._fire()
        return {
            "id": "flow-1",
            "submittedAt": "2026-09-13T00:25:12.374308Z",
            "submitted_at": datetime(2026, 9, 13, 0, 25, 12, 374308),
        }

    adapter = AfnorClientAdapter()
    with (
        patch.object(adapter, "_get_or_build_session", return_value=session),
        patch(
            "app.afnor.client.adapter.core.send_flow", side_effect=fake_send_flow_parsed
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

    assert result["submitted_at"] == datetime(2026, 9, 13, 0, 25, 12, 374308)
    trace = db_session.query(FlowTrace).one()
    assert trace.response["submitted_at"] == "2026-09-13T00:25:12.374308"


def test_send_cdar_uses_a_processing_rule_pyfrctc_accepts(db_session):
    """`pyfrctc.send_flow` valide `processing_rule` côté client contre une liste
    fermée avant tout appel réseau — on ne mocke donc pas `core.send_flow` ici
    (contrairement aux autres tests de ce module) pour vérifier réellement contre le
    code de la lib que la valeur passée est acceptée. Régression : un ancien
    `"LifeCycle"` n'en faisait pas partie et faisait échouer tout envoi de CDAR,
    indépendamment de SuperPDP (cf. app/afnor/client/adapter.py:send_cdar)."""
    company = _make_company(db_session)
    session = _fake_session_firing(request_headers={}, response_headers={})

    class _FakeHTTPSession:
        def post(self, *args, **kwargs):
            raise ConnectionError("no network in this test")

    session.post = _FakeHTTPSession().post
    session.auto_refresh_url = "https://api.superpdp.tech/oauth2/token"

    adapter = AfnorClientAdapter()
    with patch.object(adapter, "_get_or_build_session", return_value=session):
        try:
            adapter.send_cdar(db_session, company=company, cdar_bytes=b"<cdar/>")
        except ConnectionError:
            pass
        except ValueError as exc:
            assert False, f"processing_rule rejected by pyfrctc before any network call: {exc}"


def test_get_flow_document_captures_headers_and_traces_size_not_bytes(db_session):
    """`get_flow_document` (docType=Converted/ReadableView, § 4.4) relit un flux déjà
    connu de SuperPDP — le `FlowTrace` ne doit jamais contenir le binaire lui-même
    (NF1), seule sa taille, à l'image de `_send_flow_and_trace` pour `send_invoice`/
    `send_cdar`."""
    company = _make_company(db_session)
    session = _fake_session_firing(
        request_headers={"Authorization": "Bearer secret-token"},
        response_headers={"Content-Type": "application/pdf"},
    )

    def fake_get_flow(session, flow_id, doc_type=None):
        session._fire()
        return b"%PDF-fake-readable-content"

    adapter = AfnorClientAdapter()
    with (
        patch.object(adapter, "_get_or_build_session", return_value=session),
        patch("app.afnor.client.adapter.core.get_flow", side_effect=fake_get_flow),
    ):
        result = adapter.get_flow_document(
            db_session, company=company, flow_id="flow-y", doc_type="ReadableView"
        )

    assert result == b"%PDF-fake-readable-content"
    trace = db_session.query(FlowTrace).one()
    assert trace.response == {"size": len(b"%PDF-fake-readable-content")}
    assert trace.request_headers == {"Authorization": "***REDACTED***"}
    assert trace.response_headers == {"Content-Type": "application/pdf"}


def test_lookup_directory_siren_relays_the_raw_shape_not_parsed(db_session):
    """`lookup_directory_siren` doit appeler `pyfrctc.get_directory_siren` (brut :
    clés `entityType`/`administrativeStatus`/`businessName`), pas `_parsed` : ce
    proxy sert de "SuperPDP" pour un consommateur (Odoo `l10n_fr_einvoicing`) qui
    appelle LUI-MÊME `get_directory_siren_parsed` sur la réponse reçue — laquelle
    attend ces clés brutes du contrat. Relayer une forme déjà "parsée" fait
    disparaître `entityType`, que `_parsed` réinterprète alors comme "no" (absent de
    l'annuaire) même pour une entreprise bien réelle et trouvée côté SuperPDP —
    régression constatée avec un vrai SIREN actif signalé à tort comme absent."""
    company = _make_company(db_session)
    session = _fake_session_firing(request_headers={}, response_headers={})
    adapter = AfnorClientAdapter()

    raw_shape = {
        "siren": "123456782",
        "businessName": "ACME",
        "entityType": "PrivateVatRegistered",
        "administrativeStatus": "A",
    }
    with (
        patch.object(adapter, "_get_or_build_session", return_value=session),
        patch("app.afnor.client.adapter.core.get_directory_siren", return_value=raw_shape) as mock_get,
        patch("app.afnor.client.adapter.core.get_directory_siren_parsed") as mock_get_parsed,
    ):
        result = adapter.lookup_directory_siren(db_session, company=company, siren="123456782")

    mock_get.assert_called_once()
    mock_get_parsed.assert_not_called()
    assert result == raw_shape


def test_no_headers_captured_when_session_never_fires(db_session):
    """Si aucun appel HTTP n'a lieu (ex. réponse déjà en cache), les colonnes headers
    restent `None` plutôt que de fausses valeurs."""
    company = _make_company(db_session)
    session = _fake_session_firing(request_headers={}, response_headers={})
    adapter = AfnorClientAdapter()

    with (
        patch.object(adapter, "_get_or_build_session", return_value=session),
        patch(
            "app.afnor.client.adapter.core.get_directory_siren",
            return_value={"siren": "123456782"},
        ),
    ):
        result = adapter.lookup_directory_siren(db_session, company=company, siren="123456782")

    assert result == {"siren": "123456782"}
    trace = db_session.query(FlowTrace).one()
    assert trace.request_headers is None
    assert trace.response_headers is None
