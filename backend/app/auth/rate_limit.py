"""Limitation de débit en mémoire (spec.md NF6) sur les endpoints d'authentification
les plus exposés au brute-force/DoS applicatif (`POST /oauth/token`, `GET /auth/login`)
— volontairement simple (pas de dépendance externe, pas de store partagé) : le
déploiement de référence tourne avec un seul worker uvicorn (cf. README). Suffisant
comme filet de sécurité défense-en-profondeur ; un déploiement multi-worker/multi-
instance nécessiterait un store partagé (Redis...), hors périmètre actuel."""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import settings

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    """Réservé aux tests : vide l'état entre les cas de test (cf. conftest.py)."""
    with _lock:
        _hits.clear()


def rate_limit(*, scope: str, max_requests: int | None = None, window_seconds: float | None = None):
    """Fabrique une dépendance FastAPI limitant `scope` à `max_requests` requêtes par
    fenêtre glissante de `window_seconds` secondes et par adresse IP cliente — lève
    429 au-delà. Désactivable via `settings.rate_limit_enabled` (cf. conftest.py, où
    la suite de tests appelle ces mêmes endpoints bien plus souvent qu'un usage réel).

    `max_requests`/`window_seconds` sont relus depuis `settings` à chaque requête
    (pas figés à la construction de la dépendance, qui n'a lieu qu'une fois à
    l'import du router) — sinon un test qui les surcharge via `monkeypatch` après
    coup n'aurait aucun effet."""

    def dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        effective_max = max_requests if max_requests is not None else settings.rate_limit_max_requests
        effective_window = (
            window_seconds if window_seconds is not None else settings.rate_limit_window_seconds
        )
        client_ip = request.client.host if request.client else "unknown"
        key = (scope, client_ip)
        now = time.monotonic()
        with _lock:
            hits = _hits[key]
            while hits and now - hits[0] > effective_window:
                hits.popleft()
            if len(hits) >= effective_max:
                raise HTTPException(status_code=429, detail="Too many requests")
            hits.append(now)

    return dependency
