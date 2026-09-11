"""Chiffrement symétrique réversible des secrets stockés en base (spec.md § 4.10, lot 6).

Distinct du hachage irréversible (`app.auth.oauth.hash_secret`) : les identifiants que
le routeur reçoit de SuperPDP pour s'authentifier lui-même (scope `router_to_superpdp`,
§ 4.10) doivent être **récupérables** pour être présentés à chaque rafraîchissement de
jeton OAuth2 — contrairement aux identifiants que le routeur émet lui-même pour ses
consommateurs (scope `consumer_to_router`), où seul un hash suffit (§ 4.9.2)."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    key_material = (settings.secrets_encryption_key or settings.jwt_secret).encode("utf-8")
    # Fernet exige une clé de 32 octets encodée en base64 urlsafe ; on dérive une clé de
    # taille fixe à partir du secret configuré, quelle que soit sa longueur d'origine.
    derived_key = base64.urlsafe_b64encode(hashlib.sha256(key_material).digest())
    return Fernet(derived_key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Impossible de déchiffrer le secret (clé de chiffrement invalide).") from exc
