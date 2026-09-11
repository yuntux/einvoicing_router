# einvoicing_router

Routeur de factures électroniques AFNOR XP Z12-013 — voir [`spec.md`](spec.md) pour la spécification complète.

## Structure du dépôt

- `backend/` — API Python/FastAPI + SQLAlchemy (voir `spec.md` § 7.1/§ 7.3 pour la correspondance modèle/services).
- `frontend/` — IHM Vue.js (Vite).
- `docs/images/` — schémas de référence.
- `integration_tests_sandbox/` — suite d'intégration séparée contre le bac à sable SuperPDP (§ 10.4, non bloquante — voir `integration_tests_sandbox/README.md`).

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

## Installation en production (Debian / dérivés)

Procédure de référence pour déployer le routeur sur un serveur Debian/Ubuntu (ou dérivé), avec les paquets système via `apt-get`, un backend servi par `uvicorn` sous `systemd`, un frontend pré-compilé servi statiquement, et **Caddy** en reverse proxy pour le HTTPS automatique (Let's Encrypt).

### 1. Paquets système

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip build-essential git nodejs npm
```

`build-essential` est nécessaire pour compiler `cryptography` si aucune roue précompilée n'est disponible pour votre architecture/version de Python.

### 2. Utilisateur et arborescence dédiés

```bash
sudo useradd --system --create-home --home-dir /opt/einvoicing_router --shell /usr/sbin/nologin router
sudo -u router git clone https://github.com/<votre-fork>/einvoicing_router.git /opt/einvoicing_router
sudo -u router mkdir -p /opt/einvoicing_router/data/invoices
```

### 3. Backend — environnement virtuel et dépendances

```bash
cd /opt/einvoicing_router/backend
sudo -u router python3 -m venv .venv
sudo -u router .venv/bin/pip install -e .
```

(pas besoin de `[dev]` en production — ce sont les dépendances de tests uniquement.)

### 4. Configuration

#### 4.1 Enregistrer l'application dans Entra ID (NF3)

Authentification IHM (`ROUTER_OIDC_MODE=entra_id`) : créer un enregistrement d'application dans le portail Entra ID (https://entra.microsoft.com) — **App registrations**, pas *Enterprise applications* (deux vues différentes du même objet ; seule la première expose les onglets ci-dessous).

1. **Identity → Applications → App registrations → New registration**
   - *Name* : un nom parlant, ex. `Routeur factures électroniques`.
   - *Supported account types* : `Accounts in this organizational directory only (Single tenant)`, sauf besoin explicite d'ouvrir à d'autres tenants.
   - *Redirect URI* : plateforme **Web** (pas SPA/mobile — l'échange de code se fait côté serveur via Authlib), valeur exactement égale à `ROUTER_OIDC_REDIRECT_URI` ci-dessous (ex. `https://router.example.com/api/ihm/auth/callback`).
   - **Register**.
2. Sur la page **Overview** de l'app créée, relever :
   - *Application (client) ID* → `ROUTER_OIDC_CLIENT_ID`
   - *Directory (tenant) ID* → `ROUTER_OIDC_TENANT_ID`
3. **Certificates & secrets → New client secret** : choisir une description/durée, **Add**, puis copier immédiatement la colonne *Value* (affichée une seule fois) → `ROUTER_OIDC_CLIENT_SECRET`.
4. **API permissions** : vérifier la présence des permissions déléguées Microsoft Graph `openid`, `profile`, `email` (ajoutées par défaut sur un nouvel enregistrement ; sinon **Add a permission → Microsoft Graph → Delegated permissions**). Si le tenant l'exige, **Grant admin consent**.
5. *(Recommandé)* **Token configuration → Add optional claim** : type **ID**, cocher `email`, **Add** — garantit la présence de la claim `email` dans l'ID token (à défaut, le routeur se rabat sur `preferred_username`, cf. `app/api/ihm/auth.py`).

#### 4.2 Fichier `.env`

Toutes les variables sont préfixées `ROUTER_` (cf. `app/config.py`). Créer `/opt/einvoicing_router/backend/.env`, lisible uniquement par l'utilisateur `router` :

```bash
sudo -u router tee /opt/einvoicing_router/backend/.env >/dev/null <<'EOF'
# Base de données (SQLite par défaut ; chemin en dehors du dépôt pour survivre aux redéploiements)
ROUTER_DATABASE_URL=sqlite:////opt/einvoicing_router/data/router.db
ROUTER_INVOICE_STORAGE_ROOT=/opt/einvoicing_router/data/invoices

# Secrets — générer des valeurs aléatoires dédiées, distinctes du secret par défaut de dev
ROUTER_JWT_SECRET=<openssl rand -hex 32>
ROUTER_SECRETS_ENCRYPTION_KEY=<openssl rand -hex 32>

# Client AFNOR réel contre SuperPDP (§ 4.1/§ 4.8) — "fake" reste le défaut de dev/tests
ROUTER_SUPERPDP_CLIENT_MODE=pyfrctc

# Authentification IHM (NF3) — Entra ID en production, jamais "disabled"/"dev".
# Valeurs récupérées à l'étape 4.1 ci-dessus (Directory tenant ID, Application
# client ID, secret généré dans Certificates & secrets).
ROUTER_OIDC_MODE=entra_id
ROUTER_OIDC_TENANT_ID=<Directory (tenant) ID>
ROUTER_OIDC_CLIENT_ID=<Application (client) ID>
ROUTER_OIDC_CLIENT_SECRET=<valeur du client secret>
ROUTER_OIDC_REDIRECT_URI=https://router.example.com/api/ihm/auth/callback
ROUTER_FRONTEND_BASE_URL=https://router.example.com

# Allowlist IP (NF6) : le mécanisme lui-même reste actif par défaut, les listes
# d'adresses se configurent ensuite depuis l'IHM (RouterSettings), pas ici.
ROUTER_IP_ALLOWLIST_ENABLED=true
EOF
sudo chmod 600 /opt/einvoicing_router/backend/.env
```

Générer chaque secret séparément avec `openssl rand -hex 32` plutôt que de recopier la valeur d'exemple ci-dessus.

### 5. Migrations de base de données

```bash
cd /opt/einvoicing_router/backend
sudo -u router .venv/bin/alembic upgrade head
```

À rejouer à chaque déploiement d'une nouvelle version (avant de redémarrer le service, cf. § 9).

### 6. Service `systemd` — backend

Le scheduler (polling SuperPDP, retry, purge — § 4.1/§ 4.7/lot 8) tourne **en tâche de fond dans le même processus** que l'API (`APScheduler` in-process, cf. `app/main.py`) : il ne faut donc faire tourner **qu'un seul worker `uvicorn`**, jamais plusieurs (des workers multiples dupliqueraient le polling et les retries).

```ini
# /etc/systemd/system/einvoicing-router.service
[Unit]
Description=Routeur de factures électroniques — backend
After=network.target

[Service]
Type=simple
User=router
Group=router
WorkingDirectory=/opt/einvoicing_router/backend
EnvironmentFile=/opt/einvoicing_router/backend/.env
ExecStart=/opt/einvoicing_router/backend/.venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 --port 8000 --workers 1 \
    --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`--proxy-headers --forwarded-allow-ips=127.0.0.1` est nécessaire pour que le backend voie la véritable IP du client (transmise par Caddy via `X-Forwarded-For`) plutôt que `127.0.0.1` — indispensable pour que l'allowlist IP (NF6) fonctionne derrière le reverse proxy.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now einvoicing-router
```

### 7. Frontend — build statique

```bash
cd /opt/einvoicing_router/frontend
sudo -u router npm ci
# Chemin relatif : le frontend appelle l'API sur son propre domaine (même origine
# via Caddy, § 8) — pas besoin de configurer une URL absolue ni de CORS.
sudo -u router env VITE_API_BASE_URL= npm run build
```

Le résultat est généré dans `frontend/dist/` (fichiers statiques).

### 8. Caddy — reverse proxy et HTTPS automatique

```bash
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update
sudo apt-get install -y caddy
```

```caddyfile
# /etc/caddy/Caddyfile
router.example.com {
    # API et proxy émission/cycle de vie (§ 4.4) : tout ce qui commence par /api
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }

    # IHM Vue.js (SPA) : fichiers statiques, avec repli sur index.html pour le
    # routage côté client (vue-router en mode history)
    handle {
        root * /opt/einvoicing_router/frontend/dist
        try_files {path} /index.html
        file_server
    }
}
```

```bash
sudo systemctl reload caddy
```

Caddy obtient et renouvelle automatiquement un certificat Let's Encrypt pour `router.example.com` dès que le DNS pointe vers le serveur et que les ports 80/443 sont accessibles — aucune configuration TLS manuelle n'est nécessaire.

### 9. Mises à jour

```bash
cd /opt/einvoicing_router
sudo -u router git pull
cd backend && sudo -u router .venv/bin/pip install -e . && sudo -u router .venv/bin/alembic upgrade head
cd ../frontend && sudo -u router npm ci && sudo -u router env VITE_API_BASE_URL= npm run build
sudo systemctl restart einvoicing-router
sudo systemctl reload caddy
```

### 10. Sauvegardes

Les seules données à sauvegarder sont, sous `/opt/einvoicing_router/data/` : le fichier `router.db` (métadonnées, base SQLite — cf. NF5) et le répertoire `invoices/` (fichiers de factures, cf. NF8, aucune purge automatique n'y est appliquée à ce stade).
