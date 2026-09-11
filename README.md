# einvoicing_router

Routeur de factures électroniques AFNOR XP Z12-013 — voir [`spec.md`](spec.md) pour la spécification complète.

## Structure du dépôt

- `backend/` — API Python/FastAPI + SQLAlchemy (voir `spec.md` § 7.1/§ 7.3 pour la correspondance modèle/services).
- `frontend/` — IHM Vue.js (Vite).
- `docs/images/` — schémas de référence.
- `integration_tests_sandbox/` — suite d'intégration séparée contre le bac à sable SuperPDP (§ 10.4, non implémentée à ce stade).

## Développement — backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Applique les migrations (SQLite locale par défaut, cf. app/config.py)
alembic upgrade head

# Lance l'API en dev
uvicorn app.main:app --reload
```

Nouveau modèle de données : après avoir ajouté/modifié un modèle SQLAlchemy dans `app/models/`, générer une migration avec :

```bash
alembic revision --autogenerate -m "description du changement"
alembic upgrade head
```

### Tests backend (pytest)

```bash
cd backend
source .venv/bin/activate
pytest -q
```

Les tests utilisent une base SQLite **en mémoire** (jamais écrite sur disque, cf. `spec.md` § 10.2).

## Développement — frontend

```bash
cd frontend
npm install
npm run dev
```

Le frontend attend le backend sur `http://localhost:8000` (configurable via `VITE_API_BASE_URL`).

### Tests frontend (Playwright)

Le backend doit tourner (`uvicorn app.main:app` sur le port 8000, migrations appliquées) avant de lancer les tests, qui démarrent eux-mêmes le serveur de dev frontend :

```bash
cd frontend
npx playwright install --with-deps   # une seule fois
npx playwright test
```

## CI

- `.github/workflows/ci.yml` : pytest + Playwright, gate obligatoire sur chaque PR/push vers `main`.
- `.github/workflows/dependency-review.yml` : bloque l'introduction de dépendances vulnérables sur les PR.
- `.github/dependabot.yml` : veille CVE + mises à jour automatiques (pip, npm, GitHub Actions).
