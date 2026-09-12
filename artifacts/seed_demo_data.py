"""
Seed de données de démonstration — Routeur de factures électroniques

Peuple une base de démo jetable avec un jeu de données cohérent (entreprises,
fournisseurs, applications cibles, règles de routage, factures, cycle de vie,
échecs de routage, traces AFNOR, utilisateurs, contacts, configuration) via les
VRAIS endpoints HTTP du backend — mêmes règles métier/validations qu'un usage réel
(y compris la connexion : le backend de démo tourne en `ROUTER_OIDC_MODE=dev`, pas
`disabled`, § seed_demo_data() se connecte elle-même en admin avant tout le reste),
jamais de ligne injectée directement en base (cf. la docstring de generate_demo.py :
"la démo EST le seed").

Extrait de `generate_demo.py` (qui importe ce module et l'appelle juste avant sa
capture vidéo scriptée, § main()) pour pouvoir aussi tourner seul, sans lancer tout
le pipeline vidéo (edge-tts/MoviePy/Playwright) — utile pour simplement rafraîchir
la base de démo entre deux essais manuels dans le navigateur.

EXÉCUTION AUTONOME :
--------------------
python3 artifacts/seed_demo_data.py
# Réutilise un backend de démo déjà démarré sur ROUTER_DEMO_BACKEND_PORT (8299 par
# défaut) s'il y en a un ; sinon en démarre un lui-même (mêmes ports/base jetable que
# generate_demo.py, dans artifacts/temp_demo_db/), puis le laisse tourner une fois le
# seed terminé.
"""

import os
import socket
import subprocess
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

# --- CONFIGURATION (mêmes défauts/ports que generate_demo.py, § base jetable) ---
BASE_DIR = Path(__file__).parent.absolute()
ROOT_DIR = BASE_DIR.parent
BACKEND_DIR = ROOT_DIR / "backend"
DEMO_DB_DIR = BASE_DIR / "temp_demo_db"
DEMO_DB_DIR.mkdir(exist_ok=True)

DEMO_BACKEND_PORT = int(os.environ.get("ROUTER_DEMO_BACKEND_PORT", "8299"))
BACKEND_URL = f"http://localhost:{DEMO_BACKEND_PORT}"
DEMO_DB_PATH = DEMO_DB_DIR / "demo_router.db"
# Isolé du VRAI répertoire de stockage des factures (backend/.env,
# ROUTER_INVOICE_STORAGE_ROOT en prod/dev local) — jamais les données réelles.
DEMO_INVOICE_STORAGE_ROOT = DEMO_DB_DIR / "invoices"
# Identité admin par défaut pour l'exécution autonome (§ main()) — même convention
# que generate_demo.py (DEMO_ADMIN_EMAIL/NAME), qui passe la sienne explicitement à
# `seed_demo_data()` pour partager le même compte que sa capture Playwright.
DEMO_ADMIN_EMAIL = "alice.admin@example.com"
DEMO_ADMIN_NAME = "Alice Administrateur"


def _valid_siren(prefix8: str) -> str:
    """Complète un préfixe à 8 chiffres par la clé de contrôle Luhn (§ validate_siren
    côté backend, même algorithme que `uniqueValidSiren()` des tests e2e front)."""
    for check_digit in range(10):
        candidate = f"{prefix8}{check_digit}"
        total = 0
        for i, ch in enumerate(reversed(candidate)):
            d = int(ch)
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        if total % 10 == 0:
            return candidate
    raise RuntimeError(f"Aucune clé de contrôle Luhn valide pour le préfixe {prefix8!r}")


SEED_COMPANIES = [
    {"siren": _valid_siren("90000000"), "name": "Turbotop"},
    {"siren": _valid_siren("90000001"), "name": "Filgood"},
]

# Seulement 2 applications cibles seedées (§ demande utilisateur : pas de canal
# générique par entreprise, et pas d'"Odoo" ici — celui-ci est créé EN DIRECT par
# generate_demo.capture() sur sa propre société de démo, § 02_target_applications)
# — rattachées à `companies[0]` (une application cible a forcément UNE entreprise,
# § TargetApplication.company_id) ; `companies[1]` n'a aucun canal configuré, ses
# factures simulées restent donc "non routées" (§ 4.7).
SEED_TARGET_APPLICATIONS = [
    {"name": "Spendesk", "routing_method": "mail", "parameters": {"to": ["compta@spendesk.example"]}},
    {
        "name": "Expert comptable",
        "routing_method": "mail",
        "parameters": {"to": ["contact@expert-comptable.example"]},
    },
]

SEED_PARTNERS = [
    {"siren": _valid_siren("80000000"), "name": "Papeterie Générale SA"},
    {"siren": _valid_siren("80000001"), "name": "Transporteur Rapide Express"},
    {"siren": _valid_siren("80000002"), "name": "Energie Plus Fournitures"},
    {"siren": _valid_siren("80000003"), "name": "Consulting RH Partners"},
    {"siren": _valid_siren("80000004"), "name": "Matériel Informatique SA"},
    {"siren": _valid_siren("80000005"), "name": "Nettoyage Pro Services"},
    {"siren": _valid_siren("80000006"), "name": "Assurances Sécurité Plus"},
    {"siren": _valid_siren("80000007"), "name": "Imprimerie du Centre"},
]

SEED_SYNTAXES = ["Factur-X", "UBL", "CII"]
SEED_PROCESSING_RULES = ["B2B", "B2G"]


def reset_demo_database(*, db_path: Path, invoice_storage_root: Path) -> None:
    """Repart d'une base de démo vierge (§ jetable) : sans ça, `seed_demo_data()`
    ci-dessous échouerait sur des SIREN/emails déjà pris par la précédente exécution
    (contraintes d'unicité), ou accumulerait indéfiniment des doublons de factures
    d'un run à l'autre. Supprime aussi le stockage de fichiers de factures associé —
    jamais la base réelle (`backend/data/`), toujours la base jetable désignée par
    `db_path`.

    N'appeler que si aucun backend n'utilise déjà ce fichier (cf. `main()`
    ci-dessous) : supprimer la base d'un processus qui l'a encore ouverte lui laisse
    un descripteur de fichier orphelin (silencieusement inoffensif tant qu'il tourne,
    mais il repartirait de zéro, tables comprises, à son prochain redémarrage)."""
    print("🧹 Réinitialisation de la base de démo (fichiers jetables)...")
    for path in (db_path, Path(f"{db_path}-shm"), Path(f"{db_path}-wal")):
        if path.exists():
            path.unlink()
    if invoice_storage_root.exists():
        shutil.rmtree(invoice_storage_root)


# --- SEED DE DONNÉES DE DÉMONSTRATION ---
# Peuple la base de démo via les vrais endpoints HTTP du backend de démo déjà
# démarré (mêmes règles métier/validations qu'un usage réel — cf. docstring du
# module : "la démo EST le seed") : bien plus de matière que la seule histoire
# scriptée de `generate_demo.capture()` (une société, un fournisseur, une facture),
# pour que chaque écran de l'IHM montre plusieurs lignes lors d'une navigation
# manuelle, pas seulement pendant la vidéo. La séquence scriptée de capture()
# s'ajoute ensuite par-dessus (nouvelle société "Ma Société Demo", nouveau
# fournisseur "Fournisseur Demo") sans collision, ni dépendance à l'ordre.
def seed_demo_data(*, backend_url: str, admin_email: str, admin_name: str) -> None:
    """Peuple la base de démo (entreprises, fournisseurs, applications cibles,
    règles de routage, factures, cycle de vie, échecs de routage, traces AFNOR,
    utilisateurs, contacts, configuration) via les vrais endpoints HTTP du backend
    de démo — tolère un échec ponctuel par entrée (log un avertissement, continue),
    plutôt que de faire échouer toute la préparation pour une seule collision.

    Commence par se connecter en admin (`GET /api/ihm/auth/login`, § mode `dev`,
    seule façon de passer les dépendances `require_current_user`/`require_admin`
    désormais en vigueur — cf. `app/auth/session.py`) : la base venant d'être
    réinitialisée, cette première connexion amorce elle-même le compte admin
    (`user_service.resolve_login_user`, "si la table users est vide") — inutile de
    le pré-provisionner séparément. Le même email, passé par `generate_demo.py` à sa
    propre capture Playwright, permet de retrouver EXACTEMENT ce compte (retrouvé
    par `oidc_subject`, pas ré-amorcé)."""
    import requests

    print("🌱 Phase Seed — remplissage de la base de démo...")
    session = requests.Session()

    def call(method, path, **kwargs):
        resp = session.request(method, f"{backend_url}{path}", timeout=15, **kwargs)
        resp.raise_for_status()
        return resp.json() if resp.content else None

    # --- Connexion admin (amorce le compte si la base est vierge, § docstring) ---
    # `allow_redirects=False` : on n'a besoin QUE du Set-Cookie porté par la redirection
    # elle-même, pas de suivre vers `frontend_base_url` (qui ne tourne pas forcément dans
    # cette exécution autonome, § docstring du module). Mais ne PAS vérifier le statut ici a
    # déjà produit un faux succès silencieux en testant ce script : un login rejeté (ex. par le
    # rate limiter `ihm_login`, § app/auth/rate_limit.py — atteint après plusieurs exécutions
    # rapprochées pendant le débogage) répond par un statut d'erreur SANS Set-Cookie ; comme
    # rien ne vérifiait ce statut, le message "✅ Connecté" s'affichait quand même, et tous les
    # appels suivants échouaient ensuite en 401 sans explication. On vérifie donc explicitement
    # via `/auth/me` que la session posée est bien authentifiée avant de continuer.
    try:
        login_resp = session.get(
            f"{backend_url}/api/ihm/auth/login",
            params={"email": admin_email, "name": admin_name},
            allow_redirects=False,
            timeout=15,
        )
        me = session.get(f"{backend_url}/api/ihm/auth/me", timeout=15)
        me.raise_for_status()
        if not me.json().get("authenticated"):
            print(
                f"  ❌ Connexion admin refusée (statut login {login_resp.status_code}, "
                f"pas de session authentifiée ensuite) — seed interrompu. Si le backend vient "
                f"d'être relancé plusieurs fois de suite, le rate limiter 'ihm_login' "
                f"(ROUTER_RATE_LIMIT_MAX_REQUESTS/WINDOW_SECONDS) peut être en cause : "
                f"réessayer après quelques secondes."
            )
            return
        print(f"  ✅ Connecté en tant que {admin_name} ({admin_email})")
    except Exception as e:
        print(f"  ❌ Connexion admin échouée, seed interrompu : {e}")
        return

    # --- Entreprises (+ identifiants de plateforme certifiée pour certaines) ---
    companies = []
    for i, spec in enumerate(SEED_COMPANIES):
        try:
            company = call("POST", "/api/ihm/companies", json=spec)
            companies.append(company)
            print(f"  ✅ Entreprise créée : {spec['name']}")
        except Exception as e:
            print(f"  ⚠️  Entreprise '{spec['name']}' : {e}")
    for company in companies[:1]:
        try:
            call(
                "PUT",
                f"/api/ihm/companies/{company['id']}/certified-platform-credentials",
                json={"client_id": f"demo-client-{company['id']}", "client_secret": "demo-secret-not-real"},
            )
        except Exception as e:
            print(f"  ⚠️  Identifiants plateforme certifiée ({company['name']}) : {e}")

    # --- Fournisseurs (annuaire) ---
    partners = []
    for spec in SEED_PARTNERS:
        try:
            partners.append(call("POST", "/api/ihm/partners", json=spec))
        except Exception as e:
            print(f"  ⚠️  Fournisseur '{spec['name']}' : {e}")
    print(f"  ✅ {len(partners)} fournisseurs créés")

    if not companies or not partners:
        print("  ❌ Aucune entreprise/fournisseur créé, seed interrompu.")
        return

    # --- Applications cibles (2 seules, § SEED_TARGET_APPLICATIONS ci-dessus) —
    # toutes rattachées à `companies[0]` : `companies[1]` n'a aucun canal de sortie.
    main_company = companies[0]
    target_apps = {}
    for spec in SEED_TARGET_APPLICATIONS:
        try:
            target_apps[spec["name"]] = call(
                "POST",
                "/api/ihm/target-applications",
                json={
                    "name": spec["name"],
                    "routing_method": spec["routing_method"],
                    "company_id": main_company["id"],
                    "parameters": spec["parameters"],
                },
            )
        except Exception as e:
            print(f"  ⚠️  Application cible '{spec['name']}' : {e}")
    print(f"  ✅ {len(target_apps)} applications cibles créées (Spendesk, Expert comptable)")

    # --- Règles de routage (fournisseurs -> les 2 canaux de `main_company`) ---
    # 3 fournisseurs routés (Spendesk seul / Expert comptable seul / les deux à la
    # fois) et 1 fournisseur volontairement SANS règle (déclenche l'alerte "nouveau
    # fournisseur sans règle de routage", § 4.7, et son affichage en rouge, § 4.3) —
    # les fournisseurs restants n'invoicent que `companies[1]` (aucun canal
    # configuré là-bas, § plus bas : toutes ses factures sont "non routées", même
    # scénario d'alerte sans avoir à y créer de règle).
    routing_plan = []
    if "Spendesk" in target_apps:
        routing_plan.append((partners[0], [target_apps["Spendesk"]]))
    if "Expert comptable" in target_apps:
        routing_plan.append((partners[1], [target_apps["Expert comptable"]]))
    if "Spendesk" in target_apps and "Expert comptable" in target_apps:
        routing_plan.append((partners[2], [target_apps["Spendesk"], target_apps["Expert comptable"]]))
    unrouted_partner = partners[3]

    for partner, targets in routing_plan:
        for target in targets:
            try:
                call(
                    "PUT",
                    f"/api/ihm/routing-rules/{partner['id']}/{target['id']}",
                    json={"active": True, "reroute_existing": True},
                )
            except Exception as e:
                print(f"  ⚠️  Règle de routage ({partner['name']} -> {target['name']}) : {e}")
    print("  ✅ Règles de routage activées")

    # --- Factures reçues (simulées, § endpoint réservé aux tests) ---
    invoices = []
    for j, (partner, _targets) in enumerate(routing_plan):
        for k in range(2):
            invoice_date = (datetime.now() - timedelta(days=3 + (j + k) * 4)).strftime("%Y-%m-%d")
            try:
                invoice = call(
                    "POST",
                    "/api/test/invoices/simulate",
                    json={
                        "company_id": main_company["id"],
                        "emitter_siren": partner["siren"],
                        "emitter_name": partner["name"],
                        "invoice_number": f"FAC-{main_company['id']}-{partner['id']}-{k}",
                        "invoice_date": invoice_date,
                        "invoice_type": "credit_note" if (j + k) % 5 == 0 else "invoice",
                        "amount_total": round(120.0 + (j + 1) * (k + 1) * 37.5, 2),
                        "amount_excl_tax": round(100.0 + (j + 1) * (k + 1) * 31.25, 2),
                        "syntax": SEED_SYNTAXES[(j + k) % len(SEED_SYNTAXES)],
                        "processing_rule": SEED_PROCESSING_RULES[j % len(SEED_PROCESSING_RULES)],
                    },
                )
                invoices.append(invoice)
            except Exception as e:
                print(f"  ⚠️  Facture simulée ({main_company['name']} / {partner['name']}) : {e}")

    # Fournisseur sans règle chez `main_company` (alerte "nouveau fournisseur").
    try:
        invoice = call(
            "POST",
            "/api/test/invoices/simulate",
            json={
                "company_id": main_company["id"],
                "emitter_siren": unrouted_partner["siren"],
                "emitter_name": unrouted_partner["name"],
                "invoice_number": f"FAC-{main_company['id']}-{unrouted_partner['id']}-UNROUTED",
                "invoice_date": datetime.now().strftime("%Y-%m-%d"),
                "amount_total": 800.0,
                "amount_excl_tax": 666.67,
            },
        )
        invoices.append(invoice)
    except Exception as e:
        print(f"  ⚠️  Facture non routée ({main_company['name']}) : {e}")

    # `companies[1]` : aucun canal configuré (§ ci-dessus) — toutes ses factures
    # restent "non routées", quel que soit le fournisseur.
    if len(companies) > 1:
        second_company = companies[1]
        for partner in partners[5:7]:
            try:
                invoice = call(
                    "POST",
                    "/api/test/invoices/simulate",
                    json={
                        "company_id": second_company["id"],
                        "emitter_siren": partner["siren"],
                        "emitter_name": partner["name"],
                        "invoice_number": f"FAC-{second_company['id']}-{partner['id']}-UNROUTED",
                        "invoice_date": datetime.now().strftime("%Y-%m-%d"),
                        "amount_total": 450.0,
                        "amount_excl_tax": 375.0,
                    },
                )
                invoices.append(invoice)
            except Exception as e:
                print(f"  ⚠️  Facture non routée ({second_company['name']} / {partner['name']}) : {e}")
    print(f"  ✅ {len(invoices)} factures simulées")

    # --- Cycle de vie (statuts saisis manuellement) ---
    lifecycle_specs = [
        {"status": "approved"},
        {"status": "dispute", "reason": "Montant facturé supérieur au bon de commande"},
        {"status": "partially_approved", "reason": "Une ligne de la facture reste à valider"},
    ]
    for invoice, spec in zip(invoices, lifecycle_specs):
        try:
            call("POST", f"/api/ihm/invoices/{invoice['id']}/lifecycle-events", json=spec)
        except Exception as e:
            print(f"  ⚠️  Cycle de vie (facture {invoice.get('invoice_number')}) : {e}")

    # --- Téléchargements (marque `downloaded`, alimente le journal d'audit) ---
    for invoice in invoices[:3]:
        try:
            session.get(f"{backend_url}/api/ihm/invoices/{invoice['id']}/download", timeout=15)
        except Exception as e:
            print(f"  ⚠️  Téléchargement (facture {invoice.get('invoice_number')}) : {e}")

    # --- Cycle d'envoi forcé (échecs mail réalistes : aucun serveur SMTP configuré,
    #     § comportement volontairement inchangé, cf. section 06 de
    #     generate_demo.capture()) puis rejeu manuel d'une partie des échecs
    #     (-> échec définitif, pour varier l'état affiché sur la page Échecs de
    #     routage entre "à réessayer" et "échec définitif"). ---
    try:
        session.post(f"{backend_url}/api/ihm/invoice-routings/run-send-cycle", timeout=15)
        failed = call("GET", "/api/ihm/invoice-routings/failed") or []
        replay_ids = [row["id"] for row in failed[: max(1, len(failed) // 2)]]
        if replay_ids:
            call("POST", "/api/ihm/invoice-routings/replay", json={"routing_ids": replay_ids})
        print(f"  ✅ Cycle d'envoi forcé ({len(failed)} échecs, {len(replay_ids)} rejoués)")
    except Exception as e:
        print(f"  ⚠️  Cycle d'envoi forcé : {e}")

    # Pas de canal AFNOR API dans ce seed (§ SEED_TARGET_APPLICATIONS ci-dessus :
    # "Odoo" est créé EN DIRECT par generate_demo.capture()) — donc pas de trace
    # AFNOR (FlowTrace) générée ici ; la table reste vide tant que la vidéo complète
    # n'a pas tourné (capture() affiche les identifiants OAuth d'Odoo mais ne fait
    # lui-même aucun appel /oauth/token ni /flows/search).

    # --- Gestion des accès (utilisateurs) --- (l'admin lui-même, `admin_email`, a
    # déjà été provisionné par la connexion en tout début de fonction, ci-dessus.)
    seed_users = [
        {"email": "bruno.compta@example.com", "role": "user", "company_ids": [c["id"] for c in companies]},
        {"email": "claire.gestion@example.com", "role": "user", "company_ids": [companies[0]["id"]]},
        {"email": "denis.inactif@example.com", "role": "user", "company_ids": [companies[-1]["id"]], "is_active": False},
    ]
    for spec in seed_users:
        try:
            user = call("POST", "/api/ihm/users", json={"email": spec["email"]})
            call(
                "PUT",
                f"/api/ihm/users/{user['id']}/access",
                json={
                    "role": spec["role"],
                    "company_ids": spec["company_ids"],
                    "is_active": spec.get("is_active", True),
                },
            )
        except Exception as e:
            print(f"  ⚠️  Utilisateur '{spec['email']}' : {e}")
    print(f"  ✅ {len(seed_users)} utilisateurs supplémentaires créés")

    # --- Gestionnaires de facturation + configuration générale ---
    for email in ("gestionnaire1@example.com", "gestionnaire2@example.com"):
        try:
            call("POST", "/api/ihm/settings/billing-manager-contacts", json={"email": email})
        except Exception as e:
            print(f"  ⚠️  Gestionnaire de facturation '{email}' : {e}")
    try:
        call("PUT", "/api/ihm/settings", json={"technical_log_retention_days": 400})
    except Exception as e:
        print(f"  ⚠️  Configuration générale : {e}")

    print("🌱 Phase Seed terminée.")


def seed_technical_logs(*, backend_dir: Path, db_path: Path, invoice_storage_root: Path) -> None:
    """`TechnicalLog` (§ 6.1, lot 8) n'est alimenté que par le job de polling
    périodique (`app.scheduler.polling_job`, côté backend) — aucun endpoint HTTP ne
    le déclenche à la demande. On l'appelle ici directement, une fois, dans le même
    environnement (mode fake, même base) que le backend de démo : un cycle de plus,
    sans invoice à ingérer (`FakeCertifiedPlatformClient` sans fixture, §
    app/services/client_factory.py), reste un résultat de polling parfaitement
    réaliste (succès, 0 nouvelle facture) pour chaque entreprise déjà créée à ce
    stade — la seule façon d'obtenir des lignes dans "Traces & journaux > Traces
    techniques" sans attendre `polling_interval_minutes` (15 min par défaut)."""
    print("🌱 Traces techniques (cycle de polling manuel)...")
    script = (
        "from app.db.session import SessionLocal\n"
        "from app.scheduler.polling_job import run_polling_cycle\n"
        "db = SessionLocal()\n"
        "try:\n"
        "    run_polling_cycle(db)\n"
        "finally:\n"
        "    db.close()\n"
    )
    env = {
        **os.environ,
        "ROUTER_DATABASE_URL": f"sqlite:///{db_path}",
        "ROUTER_CERTIFIED_PLATFORM_CLIENT_MODE": "fake",
        "ROUTER_INVOICE_STORAGE_ROOT": str(invoice_storage_root),
    }
    try:
        subprocess.run(
            [str(backend_dir / ".venv/bin/python"), "-c", script],
            cwd=str(backend_dir), env=env, check=True, timeout=30,
        )
        print("  ✅ Traces techniques générées")
    except Exception as e:
        print(f"  ⚠️  Traces techniques : {e}")


# --- EXÉCUTION AUTONOME (sans generate_demo.py) ---
def _is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _start_demo_backend() -> None:
    # ROUTER_OIDC_MODE=dev (pas disabled) : `seed_demo_data()` se connecte en admin
    # (§ sa docstring) — indispensable depuis que les dépendances
    # `require_current_user`/`require_admin` sont réellement appliquées. Pas besoin
    # de ROUTER_FRONTEND_BASE_URL ici (contrairement à generate_demo.py) : le login
    # HTTP autonome de `seed_demo_data()` n'suit jamais la redirection
    # (`allow_redirects=False`), et aucun frontend ne tourne dans ce mode autonome.
    cmd = [
        "bash", "-c",
        f"cd {BACKEND_DIR} && "
        f"ROUTER_OIDC_MODE=dev ROUTER_DATABASE_URL=sqlite:///{DEMO_DB_PATH} "
        f"ROUTER_CERTIFIED_PLATFORM_CLIENT_MODE=fake ROUTER_INVOICE_STORAGE_ROOT={DEMO_INVOICE_STORAGE_ROOT} "
        f".venv/bin/alembic upgrade head && "
        f"ROUTER_OIDC_MODE=dev ROUTER_DATABASE_URL=sqlite:///{DEMO_DB_PATH} "
        f"ROUTER_CERTIFIED_PLATFORM_CLIENT_MODE=fake ROUTER_INVOICE_STORAGE_ROOT={DEMO_INVOICE_STORAGE_ROOT} "
        f".venv/bin/uvicorn app.main:app --host 127.0.0.1 --port {DEMO_BACKEND_PORT}",
    ]
    subprocess.Popen(cmd, cwd=str(BACKEND_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_for_backend() -> bool:
    import requests

    print(f"⏳ Attente du backend de démo sur le port {DEMO_BACKEND_PORT}...")
    for _ in range(60):
        if _is_port_open(DEMO_BACKEND_PORT):
            try:
                if requests.get(BACKEND_URL, timeout=2).status_code < 500:
                    print("  ✅ Backend de démo opérationnel.")
                    return True
            except Exception:
                pass
        time.sleep(3)
    return False


def main() -> None:
    """Exécution autonome : réutilise un backend de démo déjà démarré s'il y en a un
    sur `DEMO_BACKEND_PORT` (ne touche alors PAS à sa base — la réinitialiser sous
    les pieds d'un processus qui l'a déjà ouverte le laisserait repartir de zéro à
    son prochain redémarrage, cf. `reset_demo_database()`), sinon en démarre un
    lui-même sur une base tout juste réinitialisée."""
    if _is_port_open(DEMO_BACKEND_PORT):
        print(
            f"ℹ️  Un service tourne déjà sur le port {DEMO_BACKEND_PORT} — réutilisé "
            "tel quel (pas de réinitialisation de sa base, pour ne pas perturber un "
            "processus en cours)."
        )
    else:
        reset_demo_database(db_path=DEMO_DB_PATH, invoice_storage_root=DEMO_INVOICE_STORAGE_ROOT)
        print(f"🚀 Lancement d'un backend de démo jetable sur le port {DEMO_BACKEND_PORT}...")
        _start_demo_backend()
        if not _wait_for_backend():
            print(f"❌ Le backend de démo n'a pas démarré à temps sur le port {DEMO_BACKEND_PORT}.")
            return

    seed_demo_data(backend_url=BACKEND_URL, admin_email=DEMO_ADMIN_EMAIL, admin_name=DEMO_ADMIN_NAME)
    seed_technical_logs(
        backend_dir=BACKEND_DIR, db_path=DEMO_DB_PATH, invoice_storage_root=DEMO_INVOICE_STORAGE_ROOT
    )
    print(f"✨ Base de démo prête : {BACKEND_URL}")


if __name__ == "__main__":
    main()
