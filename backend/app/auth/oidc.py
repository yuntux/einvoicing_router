"""Client OIDC réel contre Microsoft Entra ID (spec.md NF3, lot 7) — construit sur
**Authlib** (`authlib.integrations.starlette_client`) plutôt que réimplémenté à la
main : Authlib gère nativement la découverte OpenID Connect, PKCE, state/nonce
(stockés côté serveur via `starlette.middleware.sessions.SessionMiddleware`, cf.
`app.main`) et la validation de l'ID token (signature JWKS, émetteur, audience,
nonce). Ce module se contente d'enregistrer le client avec la configuration
courante — `app/api/ihm/auth.py` appelle directement les méthodes Authlib
(`authorize_redirect`/`authorize_access_token`)."""

from authlib.integrations.starlette_client import OAuth

from app.config import settings

oauth = OAuth()

CLIENT_NAME = "entra_id"


def entra_id_client():
    """(Ré)enregistre le client à chaque appel avec la configuration courante :
    `settings.oidc_*` peut changer sans redémarrage du process (tenant/app OIDC
    reconfigurable depuis l'IHM à terme). Authlib met en cache le client construit
    dès son premier accès (`oauth._clients`) — on l'invalide explicitement pour que
    la configuration courante soit toujours prise en compte."""
    oauth._clients.pop(CLIENT_NAME, None)
    oauth.register(
        name=CLIENT_NAME,
        server_metadata_url=(
            f"https://login.microsoftonline.com/{settings.oidc_tenant_id}"
            "/v2.0/.well-known/openid-configuration"
        ),
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        client_kwargs={"scope": "openid profile email"},
    )
    return oauth.create_client(CLIENT_NAME)
