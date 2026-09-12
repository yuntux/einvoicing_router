"""Séparation des secrets de signature/chiffrement (§ 4.10/NF3) : `jwt_secret`
(jetons OAuth Odoo), `session_secret` (jetons de session IHM) et
`secrets_encryption_key` (chiffrement des identifiants SuperPDP) sont trois secrets
indépendants, sans repli de l'un sur l'autre — la fuite d'un seul ne doit jamais
compromettre les deux autres usages, ni permettre de rejouer un jeton d'un type à la
place de l'autre."""

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from app.auth.oauth import (
    _ClientWrapper,
    _generate_bearer_token,
    generate_client_credentials,
    get_current_target_application,
    hash_secret,
)
from app.auth.session import _decode_session_token, issue_session_token
from app.config import settings
from app.models.referential import Company, RoutingMethod, TargetApplication, User
from app.services.secrets_encryption import decrypt_secret, encrypt_secret


def _make_user(db, email="user@example.com", role="user"):
    user = User(email=email, name="Test", role=role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_oauth_app(db):
    """Une application `afnor_api` EST le "client" OAuth (§ 4.9.2/§ 4.10)."""
    company = Company(siren="123456789", name="Test")
    db.add(company)
    db.commit()
    db.refresh(company)

    client_id, secret = generate_client_credentials()
    target = TargetApplication(
        name="Odoo",
        routing_method=RoutingMethod.AFNOR_API,
        company_id=company.id,
        parameters={
            "client_id": client_id,
            "client_secret_hash": hash_secret(secret),
            "app_type": "confidential",
        },
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def test_session_token_rejected_as_oauth_bearer_token(db_session):
    """Un jeton de session IHM ne doit jamais être accepté comme jeton d'application
    OAuth, même s'il est correctement signé (secrets déjà distincts + claim `typ`)."""
    user = _make_user(db_session)
    session_token = issue_session_token(user)

    with pytest.raises(HTTPException) as exc_info:
        get_current_target_application(authorization=f"Bearer {session_token}", db=db_session)
    assert exc_info.value.status_code == 401


def test_oauth_token_rejected_as_session_cookie(db_session):
    """Symétriquement, un jeton OAuth émis pour Odoo ne doit jamais être accepté
    comme jeton de session IHM."""
    oauth_app = _make_oauth_app(db_session)
    token = _generate_bearer_token(
        "client_credentials", _ClientWrapper(oauth_app)
    )["access_token"]

    with pytest.raises(pyjwt.PyJWTError):
        _decode_session_token(token)


def test_secrets_encryption_never_falls_back_to_jwt_secret(monkeypatch):
    """`secrets_encryption_key` ne doit jamais dépendre de `jwt_secret` — un secret
    de signature JWT qui change (rotation, fuite...) ne doit jamais affecter le
    chiffrement/déchiffrement des identifiants SuperPDP au repos."""
    monkeypatch.setattr(settings, "secrets_encryption_key", "fixed-encryption-key")
    monkeypatch.setattr(settings, "jwt_secret", "jwt-secret-value-one")
    ciphertext = encrypt_secret("super-pdp-client-secret")

    monkeypatch.setattr(settings, "jwt_secret", "completely-different-jwt-secret")
    assert decrypt_secret(ciphertext) == "super-pdp-client-secret"


def test_jwt_session_and_encryption_secrets_have_distinct_defaults():
    """Les valeurs par défaut (dev) telles qu'écrites dans le code sont déjà deux à
    deux distinctes — la confusion entre jetons de session, jetons OAuth et clé de
    chiffrement au repos n'est pas seulement empêchée par la claim `typ`, mais aussi
    structurellement par défaut, sans configuration requise. Inspecte directement
    les défauts du modèle Pydantic plutôt que `settings` (potentiellement surchargé
    par les variables d'environnement du process de test)."""
    from app.config import Settings

    defaults = {
        name: Settings.model_fields[name].default
        for name in ("jwt_secret", "session_secret", "secrets_encryption_key")
    }
    assert len(set(defaults.values())) == 3
