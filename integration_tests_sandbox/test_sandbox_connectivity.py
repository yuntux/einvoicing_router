"""Connectivité réelle au bac à sable SuperPDP (spec.md § 10.4) — jamais exécutée par
la CI bloquante, ignorée automatiquement sans identifiants (cf. conftest.py)."""

from datetime import datetime, timedelta

from pyfrctc import pyfrctc as core

from app.config import settings


def _build_session(sandbox_credentials):
    token_state: dict = {}

    def get_token_method(grant_type: str) -> dict:
        return {
            "access_token": token_state.get("access_token"),
            "expires_at": token_state.get("expires_at"),
        }

    def update_token_method(token: dict) -> None:
        token_state.update(token)

    return core.get_session(
        platform=settings.superpdp_platform,
        auth_method="client_credentials",
        company_ident4log=sandbox_credentials["company_siren"],
        get_token_method=get_token_method,
        update_token_method=update_token_method,
        client_id=sandbox_credentials["client_id"],
        client_secret=sandbox_credentials["client_secret"],
    )


def test_healthcheck(sandbox_credentials):
    session = _build_session(sandbox_credentials)
    core.healthcheck(session, raise_if_error=True)


def test_directory_lookup_own_siren(sandbox_credentials):
    session = _build_session(sandbox_credentials)
    result = core.get_directory_siren_parsed(session, sandbox_credentials["company_siren"])
    assert result["siren"] == sandbox_credentials["company_siren"]


def test_search_flows_recent(sandbox_credentials):
    """Vérifie que le polling réel (§ 4.1) répond, sans dépendre du contenu exact
    (le bac à sable peut être vide) — la connectivité/authentification suffit ici."""
    session = _build_session(sandbox_credentials)
    flows = core.search_flows_parsed(
        session,
        updated_after=datetime.utcnow() - timedelta(days=30),
        flow_direction="in",
        flow_type=["SupplierInvoice", "SupplierInvoiceLC"],
    )
    assert isinstance(flows, list)
