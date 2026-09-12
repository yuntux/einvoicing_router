"""
Seed de données de démonstration — Routeur de factures électroniques

Peuple une base de démo jetable avec un jeu de données cohérent (entreprises,
fournisseurs, applications cibles, règles de routage, factures, cycle de vie,
échecs de routage, traces AFNOR, utilisateurs, contacts, configuration) via les
VRAIS endpoints HTTP du backend — mêmes règles métier/validations qu'un usage réel,
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
    {"siren": _valid_siren("90000000"), "name": "Cabinet Comptable Lefèvre & Associés"},
    {"siren": _valid_siren("90000001"), "name": "Groupe Industriel Nord"},
    {"siren": _valid_siren("90000002"), "name": "Distribution Ouest SARL"},
    {"siren": _valid_siren("90000003"), "name": "Tech Solutions Paris"},
    {"siren": _valid_siren("90000004"), "name": "Clinique Vétérinaire du Parc"},
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
def seed_demo_data(*, backend_url: str) -> None:
    """Peuple la base de démo (entreprises, fournisseurs, applications cibles,
    règles de routage, factures, cycle de vie, échecs de routage, traces AFNOR,
    utilisateurs, contacts, configuration) via les vrais endpoints HTTP du backend
    de démo — tolère un échec ponctuel par entrée (log un avertissement, continue),
    plutôt que de faire échouer toute la préparation pour une seule collision."""
    import requests

    print("🌱 Phase Seed — remplissage de la base de démo...")
    session = requests.Session()

    def call(method, path, **kwargs):
        resp = session.request(method, f"{backend_url}{path}", timeout=15, **kwargs)
        resp.raise_for_status()
        return resp.json() if resp.content else None

    # --- Entreprises (+ identifiants de plateforme certifiée pour certaines) ---
    companies = []
    for i, spec in enumerate(SEED_COMPANIES):
        try:
            company = call("POST", "/api/ihm/companies", json=spec)
            companies.append(company)
            print(f"  ✅ Entreprise créée : {spec['name']}")
        except Exception as e:
            print(f"  ⚠️  Entreprise '{spec['name']}' : {e}")
    for company in companies[:3]:
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

    # --- Applications cibles (une mail + une AFNOR API par entreprise) ---
    mail_apps, afnor_apps = {}, {}
    for company in companies:
        try:
            mail_apps[company["id"]] = call(
                "POST",
                "/api/ihm/target-applications",
                json={
                    "name": f"Comptabilité {company['name']}",
                    "routing_method": "mail",
                    "company_id": company["id"],
                    "parameters": {"to": [f"compta+{company['id']}@example.com"]},
                },
            )
            afnor_apps[company["id"]] = call(
                "POST",
                "/api/ihm/target-applications",
                json={
                    "name": f"ERP {company['name']}",
                    "routing_method": "afnor_api",
                    "company_id": company["id"],
                    "parameters": {},
                },
            )
        except Exception as e:
            print(f"  ⚠️  Applications cibles ({company['name']}) : {e}")
    print(f"  ✅ {len(mail_apps)} paires d'applications cibles créées (mail + AFNOR API)")

    # --- Règles de routage (matrice fournisseurs x applications cibles) ---
    # Pour chaque entreprise, 3 fournisseurs routés (mail seul / AFNOR API seul / les
    # deux) et 1 fournisseur volontairement SANS règle (déclenche l'alerte "nouveau
    # fournisseur sans règle de routage", § 4.7, et son affichage en rouge, § 4.3).
    routed_partners_by_company = {}
    unrouted_partner_by_company = {}
    for i, company in enumerate(companies):
        cid = company["id"]
        if cid not in mail_apps or cid not in afnor_apps:
            continue
        p_mail = partners[(i * 4) % len(partners)]
        p_afnor = partners[(i * 4 + 1) % len(partners)]
        p_both = partners[(i * 4 + 2) % len(partners)]
        p_none = partners[(i * 4 + 3) % len(partners)]
        routed_partners_by_company[cid] = [(p_mail, "mail"), (p_afnor, "afnor"), (p_both, "both")]
        unrouted_partner_by_company[cid] = p_none
        try:
            call(
                "PUT",
                f"/api/ihm/routing-rules/{p_mail['id']}/{mail_apps[cid]['id']}",
                json={"active": True, "reroute_existing": True},
            )
            call(
                "PUT",
                f"/api/ihm/routing-rules/{p_afnor['id']}/{afnor_apps[cid]['id']}",
                json={"active": True, "reroute_existing": True},
            )
            call(
                "PUT",
                f"/api/ihm/routing-rules/{p_both['id']}/{mail_apps[cid]['id']}",
                json={"active": True, "reroute_existing": True},
            )
            call(
                "PUT",
                f"/api/ihm/routing-rules/{p_both['id']}/{afnor_apps[cid]['id']}",
                json={"active": True, "reroute_existing": True},
            )
        except Exception as e:
            print(f"  ⚠️  Règles de routage ({company['name']}) : {e}")
    print("  ✅ Règles de routage activées")

    # --- Factures reçues (simulées, § endpoint réservé aux tests) ---
    invoices = []
    for i, company in enumerate(companies):
        cid = company["id"]
        for j, (partner, _kind) in enumerate(routed_partners_by_company.get(cid, [])):
            for k in range(2):
                days_ago = 3 + (i + j + k) * 4
                invoice_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
                try:
                    invoice = call(
                        "POST",
                        "/api/test/invoices/simulate",
                        json={
                            "company_id": cid,
                            "emitter_siren": partner["siren"],
                            "emitter_name": partner["name"],
                            "invoice_number": f"FAC-{cid}-{partner['id']}-{k}",
                            "invoice_date": invoice_date,
                            "invoice_type": "credit_note" if (j + k) % 5 == 0 else "invoice",
                            "amount_total": round(120.0 + (i + 1) * (j + 1) * (k + 1) * 37.5, 2),
                            "amount_excl_tax": round(100.0 + (i + 1) * (j + 1) * (k + 1) * 31.25, 2),
                            "syntax": SEED_SYNTAXES[(i + j + k) % len(SEED_SYNTAXES)],
                            "processing_rule": SEED_PROCESSING_RULES[(i + j) % len(SEED_PROCESSING_RULES)],
                        },
                    )
                    invoices.append(invoice)
                except Exception as e:
                    print(f"  ⚠️  Facture simulée ({company['name']} / {partner['name']}) : {e}")
        unrouted = unrouted_partner_by_company.get(cid)
        if unrouted:
            try:
                invoice = call(
                    "POST",
                    "/api/test/invoices/simulate",
                    json={
                        "company_id": cid,
                        "emitter_siren": unrouted["siren"],
                        "emitter_name": unrouted["name"],
                        "invoice_number": f"FAC-{cid}-{unrouted['id']}-UNROUTED",
                        "invoice_date": datetime.now().strftime("%Y-%m-%d"),
                        "amount_total": 800.0,
                        "amount_excl_tax": 666.67,
                    },
                )
                invoices.append(invoice)
            except Exception as e:
                print(f"  ⚠️  Facture non routée ({company['name']}) : {e}")
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

    # --- Traces AFNOR (FlowTrace) : jeton OAuth + recherche de flux, pour chaque
    #     application AFNOR API — endpoints purement locaux (§ pas de passthrough
    #     SuperPDP réel), sans dépendance réseau externe. ---
    for cid, app in afnor_apps.items():
        client_id, client_secret = app.get("oauth_client_id"), app.get("oauth_client_secret")
        if not client_id or not client_secret:
            continue
        try:
            token_resp = session.post(
                f"{backend_url}/api/afnor/v1/oauth/token",
                data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
                timeout=15,
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]
            session.post(
                f"{backend_url}/api/afnor/v1/afnor-flow/flows/search",
                json={"where": {}, "limit": 25},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
        except Exception as e:
            print(f"  ⚠️  Traces AFNOR (entreprise {cid}) : {e}")
    print("  ✅ Traces AFNOR générées (jeton + recherche de flux)")

    # --- Gestion des accès (utilisateurs) ---
    seed_users = [
        {"email": "alice.admin@example.com", "role": "admin", "company_ids": []},
        {"email": "bruno.compta@example.com", "role": "user", "company_ids": [c["id"] for c in companies[:2]]},
        {"email": "claire.gestion@example.com", "role": "user", "company_ids": [companies[2]["id"]] if len(companies) > 2 else []},
        {"email": "denis.inactif@example.com", "role": "user", "company_ids": [companies[3]["id"]] if len(companies) > 3 else [], "is_active": False},
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
    cmd = [
        "bash", "-c",
        f"cd {BACKEND_DIR} && "
        f"ROUTER_OIDC_MODE=disabled ROUTER_DATABASE_URL=sqlite:///{DEMO_DB_PATH} "
        f"ROUTER_CERTIFIED_PLATFORM_CLIENT_MODE=fake ROUTER_INVOICE_STORAGE_ROOT={DEMO_INVOICE_STORAGE_ROOT} "
        f".venv/bin/alembic upgrade head && "
        f"ROUTER_OIDC_MODE=disabled ROUTER_DATABASE_URL=sqlite:///{DEMO_DB_PATH} "
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

    seed_demo_data(backend_url=BACKEND_URL)
    seed_technical_logs(
        backend_dir=BACKEND_DIR, db_path=DEMO_DB_PATH, invoice_storage_root=DEMO_INVOICE_STORAGE_ROOT
    )
    print(f"✨ Base de démo prête : {BACKEND_URL}")


if __name__ == "__main__":
    main()
