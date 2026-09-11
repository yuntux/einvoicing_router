"""Suite d'intégration bac à sable SuperPDP (spec.md § 10.4) — non bloquante, jamais
exécutée par la CI principale. Réutilise l'environnement Python du backend (pyfrctc y
est déjà installé) plutôt que de dupliquer une dépendance."""

import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

REQUIRED_ENV_VARS = [
    "SUPERPDP_SANDBOX_CLIENT_ID",
    "SUPERPDP_SANDBOX_CLIENT_SECRET",
    "SUPERPDP_SANDBOX_COMPANY_SIREN",
]


def _missing_env_vars() -> list[str]:
    return [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]


@pytest.fixture(scope="session")
def sandbox_credentials():
    missing = _missing_env_vars()
    if missing:
        pytest.skip(
            "Identifiants bac à sable SuperPDP manquants "
            f"({', '.join(missing)}) — suite ignorée (spec.md § 10.4)."
        )
    return {
        "client_id": os.environ["SUPERPDP_SANDBOX_CLIENT_ID"],
        "client_secret": os.environ["SUPERPDP_SANDBOX_CLIENT_SECRET"],
        "company_siren": os.environ["SUPERPDP_SANDBOX_COMPANY_SIREN"],
    }
