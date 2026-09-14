"""
Script d'automatisation de démonstration vidéo — Routeur de factures électroniques

Ce script génère une vidéo de démonstration en combinant :
1. Narration audio (edge-tts, voix neuronale Microsoft Azure, gratuit, sans clonage).
2. Un schéma animé d'introduction — storyboard HTML/CSS/JS autonome
   (artifacts/demo_intro_animation.html, éditable/prévisualisable seul dans un navigateur),
   capturé via un second passage Playwright (§ capture_intro()) — qui pose la proposition de
   valeur du routeur avant de montrer l'application : plusieurs outils de gestion (Spendesk,
   comptable, ERP...) utilisant des protocoles différents, absorbés par le routeur derrière une
   seule adresse de facturation par SIREN.
3. Capture vidéo automatisée (Playwright) du parcours complet dans l'IHM réelle
   (Vue + Vite), contre un backend FastAPI de démonstration dédié, lancé avec
   `ROUTER_OIDC_MODE=dev` (§ NF3 — mode sans IdP réel, prévu justement pour ça) :
   la capture se connecte via `GET /api/ihm/auth/login?email=...&name=...` (même
   compte que celui utilisé pour le seed HTTP, § ci-dessous) avant toute navigation,
   pour que la vidéo montre un admin réellement connecté (pied de sidebar, journal
   d'audit attribué) plutôt qu'un accès anonyme.
4. Montage automatique (MoviePy).

Choix de voix testés à l'oreille :
- fr-FR-HenriNeural (homme, génération "Neural" standard) : rendu saccadé, écarté.
- fr-FR-RemyMultilingualNeural (homme, génération "Multilingual" plus récente) : validé, RETENU.
- fr-FR-VivienneMultilingualNeural (femme, même génération) : validée aussi, bonne alternative —
  changez juste EDGE_TTS_VOICE ci-dessous pour basculer.
Autres voix FR disponibles (régionales) : fr-BE-CharlineNeural/GerardNeural (Belgique),
fr-CA-SylvieNeural/AntoineNeural/JeanNeural/ThierryNeural (Québec),
fr-CH-ArianeNeural/FabriceNeural (Suisse) — lister avec `edge-tts --list-voices`.

Quota : edge-tts n'a pas de quota officiel publié (ce n'est pas un produit facturé, contrairement
à Azure Speech Service qui utilise les mêmes voix) mais pas de garantie de service non plus —
usage intensif/en rafale déconseillé (throttling possible). Notre usage (10 segments courts,
générés ponctuellement) est très en dessous de tout seuil réaliste.

Avant la capture, `artifacts/seed_demo_data.py` (module séparé, importé ci-dessous)
peuple la base de démo en masse via les vrais endpoints HTTP du backend (mêmes
règles métier/validations qu'un usage réel, y compris la connexion admin — cf.
docstring de ce module) : plusieurs entreprises/fournisseurs/factures/utilisateurs,
pas seulement l'unique histoire scriptée ci-dessous, pour que chaque écran de l'IHM
montre plusieurs lignes lors d'une navigation manuelle, pas seulement pendant la
vidéo. La séquence scriptée de capture() (nouvelle société "Ma Société Demo",
nouveau fournisseur "Fournisseur Demo", réception de facture via l'endpoint réservé
aux tests `POST /api/test/invoices/simulate`, monté uniquement quand
`certified_platform_client_mode == "fake"`, cf. `backend/app/api/testing/invoices.py`)
s'ajoute ensuite par-dessus, sans collision ni dépendance à l'ordre : ce qui
s'affiche à l'écran pendant la vidéo reste le résultat réel d'actions IHM
effectuées, pas un jeu de données injecté directement en base.

INSTALLATION DES DEPENDANCES :
------------------------------
sudo apt update && sudo apt install -y python3-pip python3-venv ffmpeg fonts-dejavu-core
pip install --no-cache-dir playwright moviepy edge-tts pillow requests --break-system-packages
playwright install --with-deps chromium
# edge-tts a besoin d'un accès réseau sortant (endpoint non officiel Microsoft) — pas de clé API.

EXECUTION DU SCRIPT :
---------------------
# Aucun service à démarrer manuellement au préalable : le script lance lui-même un
# backend et un frontend de démonstration dédiés (ports distincts de ceux d'une
# instance de dev/prod déjà en cours, cf. CONFIGURATION ci-dessous), sur une base
# SQLite jetable dans artifacts/temp_demo_db/.
python3 artifacts/generate_demo.py

# Mode montage seul (réutilise la dernière capture vidéo, ne relance pas Playwright) :
python3 artifacts/generate_demo.py --assemble-only

STRUCTURE DU SCRIPT :
--------------------
- CONFIGURATION : ports/DB de démonstration dédiés, réglages edge-tts, palette reprise
  de frontend/src/style.css.
- AUDIO : génération des segments MP3 via edge-tts (voix fr-FR-RemyMultilingualNeural),
  mis en cache par hash du texte.
- SCHEMA D'INTRO : capture_intro() — capture Playwright de demo_intro_animation.html
  (storyboard HTML/CSS/JS autonome, à éditer séparément), rognée à la durée du segment audio
  "00_value_prop".
- CAPTURE : navigation réelle dans l'IHM (clics de menu, remplissage de formulaires,
  confirmation des popins) via les vrais data-testid du frontend — pas de données
  pré-injectées, tout est créé pendant la capture.
- MONTAGE : capture_intro() + capture, audio calé sur les timestamps réels.
"""
import os
import asyncio
import time
import subprocess
import sys
import hashlib
import json
import socket
import urllib.parse
from datetime import datetime
from pathlib import Path

import moviepy as mp
from playwright.async_api import async_playwright

# Seed de données de démonstration (entreprises, factures, traces AFNOR...) — extrait
# dans son propre module pour pouvoir aussi tourner seul, sans lancer tout le
# pipeline vidéo (§ artifacts/seed_demo_data.py, importable tel quel : ce script et
# le seed vivent dans le même répertoire, sur le sys.path ajouté par Python lui-même
# à l'exécution directe de generate_demo.py).
import seed_demo_data as demo_seed

# --- CONFIGURATION GÉNÉRALE ---
BASE_DIR = Path(__file__).parent.absolute()
ROOT_DIR = BASE_DIR.parent
AUDIO_DIR = BASE_DIR / "temp_audio"
VIDEO_DIR = BASE_DIR / "temp_video"
DEMO_DB_DIR = BASE_DIR / "temp_demo_db"
AUDIO_DIR.mkdir(exist_ok=True)
VIDEO_DIR.mkdir(exist_ok=True)
DEMO_DB_DIR.mkdir(exist_ok=True)

BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"

# Ports DÉLIBÉRÉMENT distincts de ceux d'une instance de dev/prod déjà en cours
# (8000/5173, cf. README.md) — ce script lance ses propres services jetables, sur sa
# propre base SQLite, sans jamais toucher à une base réelle.
DEMO_BACKEND_PORT = int(os.environ.get("ROUTER_DEMO_BACKEND_PORT", "8299"))
DEMO_FRONTEND_PORT = int(os.environ.get("ROUTER_DEMO_FRONTEND_PORT", "5299"))
BASE_URL = f"http://localhost:{DEMO_FRONTEND_PORT}"
BACKEND_URL = f"http://localhost:{DEMO_BACKEND_PORT}"
DEMO_DB_PATH = DEMO_DB_DIR / "demo_router.db"
# backend/.env (config réelle de l'instance de prod/dev locale) définit
# ROUTER_INVOICE_STORAGE_ROOT vers le VRAI répertoire de stockage des factures — sans cette
# variable dédiée, les factures simulées pendant la démo (§ 04_invoices) s'écriraient dans les
# données réelles. Isolée au même titre que ROUTER_DATABASE_URL ci-dessus.
DEMO_INVOICE_STORAGE_ROOT = DEMO_DB_DIR / "invoices"
# Identité admin unique utilisée à la fois pour le login HTTP du seed en masse
# (artifacts/seed_demo_data.py) et pour la connexion Playwright de capture()
# ci-dessous — même compte (`oidc_subject` = f"dev:{email}", § app/auth/oauth.py),
# pour que la vidéo montre le même admin que celui qui apparaît déjà dans le journal
# d'audit peuplé par le seed.
DEMO_ADMIN_EMAIL = "alice.admin@example.com"
DEMO_ADMIN_NAME = "Alice Administrateur"
# DOIT être créé DANS frontend/ (pas dans artifacts/) : Vite résout les imports du fichier de
# config (`@vitejs/plugin-vue`, `vite`) en remontant l'arborescence node_modules à partir de
# l'EMPLACEMENT du fichier de config lui-même — artifacts/ et frontend/ sont des répertoires
# frères, sans chaîne node_modules commune, donc un fichier de config posé dans artifacts/ ne
# trouve jamais les modules déjà installés dans frontend/node_modules (piège découvert en testant
# ce script : erreur ERR_MODULE_NOT_FOUND alors que les paquets sont bien présents).
VITE_PROXY_CONFIG = FRONTEND_DIR / "vite.config.demo.mjs"

# Résolution de la capture Playwright ET du schéma d'intro : DOIVENT être identiques
# (MoviePy ne réconcilie pas silencieusement deux résolutions différentes lors de la
# concaténation — un décalage produit un encodage corrompu, flash/strobe sur toute la
# vidéo montée, alors que chaque clip pris séparément est propre).
VIDEO_WIDTH = 1440
VIDEO_HEIGHT = 900

# --- CONFIGURATION DE L'APPLICATION (schéma d'intro, page de garde) ---
# Palette reprise de frontend/src/style.css (--color-primary / --color-accent).
# Schéma d'intro : storyboard HTML/CSS/JS autonome (voir ce fichier pour la palette et le
# scénario), capturé tel quel via Playwright ci-dessous — plus de génération PIL séparée.
INTRO_HTML_PATH = BASE_DIR / "demo_intro_animation.html"

APP_SETTINGS = {
    "services": [
        {
            "name": "backend démo",
            "port": DEMO_BACKEND_PORT,
            "check_url": f"{BACKEND_URL}/",
            "cmd": [
                "bash", "-c",
                # Variables explicites (jamais un simple sous-ensemble) : backend/.env — le VRAI
                # fichier de config de l'instance de prod/dev locale — définit par défaut
                # ROUTER_CERTIFIED_PLATFORM_CLIENT_MODE=pyfrctc et ROUTER_OIDC_MODE=entra_id ; sans
                # les redéfinir explicitement ici, pydantic-settings les reprendrait tels quels
                # (env_file=".env", cwd=backend) et ce backend de démo se comporterait comme la
                # prod (vrai client SuperPDP, vraie authentification Entra ID) au lieu d'un backend
                # jetable en mode fixtures. ROUTER_CERTIFIED_PLATFORM_CLIENT_MODE=fake est aussi ce
                # qui monte l'endpoint réservé aux tests /api/test/invoices/simulate (§ app/main.py).
                f"cd {BACKEND_DIR} && "
                f"ROUTER_OIDC_MODE=dev ROUTER_DATABASE_URL=sqlite:///{DEMO_DB_PATH} "
                f"ROUTER_CERTIFIED_PLATFORM_CLIENT_MODE=fake "
                f"ROUTER_INVOICE_STORAGE_ROOT={DEMO_INVOICE_STORAGE_ROOT} "
                f".venv/bin/alembic upgrade head && "
                # ROUTER_OIDC_MODE=dev (au lieu de disabled) : simule une connexion admin
                # réelle (§ docstring du module) — sans identifiant IdP réel, juste un
                # email/nom passés à /api/ihm/auth/login (cf. capture() et
                # seed_demo_data.py). ROUTER_FRONTEND_BASE_URL doit pointer vers le
                # frontend de démo (BASE_URL, pas le défaut :5173) : c'est là que
                # `/api/ihm/auth/login` redirige une fois la session posée.
                f"ROUTER_OIDC_MODE=dev ROUTER_DATABASE_URL=sqlite:///{DEMO_DB_PATH} "
                f"ROUTER_CERTIFIED_PLATFORM_CLIENT_MODE=fake "
                f"ROUTER_INVOICE_STORAGE_ROOT={DEMO_INVOICE_STORAGE_ROOT} "
                f"ROUTER_FRONTEND_BASE_URL={BASE_URL} "
                f".venv/bin/uvicorn app.main:app --host 127.0.0.1 --port {DEMO_BACKEND_PORT}",
            ],
            "cwd": BACKEND_DIR,
        },
        {
            "name": "frontend démo",
            "port": DEMO_FRONTEND_PORT,
            "check_url": BASE_URL,
            # `frontend/.env.development` — le VRAI fichier de config utilisé pour le dev local
            # normal — fixe VITE_API_BASE_URL=http://localhost:8000 (le backend RÉEL) pour éviter
            # d'avoir besoin d'un proxy en dev courant. Une variable d'environnement VITE_ à
            # l'exécution a priorité sur les fichiers .env chez Vite : sans la redéfinir ici à vide,
            # le frontend de démo continuerait à appeler le VRAI backend au lieu du proxy vers le
            # backend de démo — piège découvert en testant ce script (échecs silencieux bloqués
            # par CORS, aucune donnée créée). `VITE_API_BASE_URL=""` restaure le chemin relatif
            # `/api` attendu par frontend/src/api/http.ts, capté par le proxy de VITE_PROXY_CONFIG.
            "cmd": [
                "bash", "-c",
                f"cd {FRONTEND_DIR} && VITE_API_BASE_URL= "
                f"npx vite --host 127.0.0.1 --port {DEMO_FRONTEND_PORT} --config {VITE_PROXY_CONFIG}",
            ],
            "cwd": FRONTEND_DIR,
        },
    ],
}

# --- CONFIGURATION edge-tts (voix neuronales Microsoft Azure, gratuit, non officiel) ---
# Pas de clé API, pas de modèle local. Nécessite un accès réseau sortant.
#
# Ce que edge-tts expose et que d'autres moteurs TTS basiques n'ont PAS (raison de fond :
# edge-tts donne accès aux mêmes voix neuronales que le service payant Azure Speech, via un
# point d'accès gratuit non officiel) :
#
# Déjà utilisés ci-dessous :
#   - voice  : un vrai choix parmi ~300+ voix neuronales nommées (13 en français : Remy, Vivienne,
#              Henri, Denise...), chacune avec son propre timbre/prosodie.
#   - rate   : réglage natif du débit ("+15%", "-10%"), pitch préservé, géré côté service Microsoft
#              (pas de bricolage ffmpeg `atempo` nécessaire pour accélérer sans changer la hauteur
#              de voix, comme avec un moteur n'exposant qu'un booléen slow=True/False).
#   - pitch  : décalage de hauteur ("+5Hz", "-10Hz"). Laissé à +0Hz ici, mais utilisable pour
#              changer le caractère de la voix.
#
# Disponibles mais PAS utilisés pour l'instant (pistes pour plus tard) :
#   - volume            : même principe que rate/pitch ("+20%", "-10%"), documenté dans l'API.
#   - communicate.stream() au lieu de .save() : renvoie des événements WordBoundary (début, durée
#                          de chaque mot prononcé) — permettrait de générer des sous-titres
#                          synchronisés automatiquement sur la vidéo.
#   - edge_tts.list_voices() / `edge-tts --list-voices` : catalogue interrogeable (langue, genre,
#                          catégorie) — utilisé une fois en exploration pour lister les 13 voix FR,
#                          pas appelé depuis ce script.
#
# Voix retenue après comparaison à l'oreille (voir docstring) — homme, génération "Multilingual"
# récente, jugée fluide (contrairement à fr-FR-HenriNeural, plus ancienne, saccadée).
EDGE_TTS_VOICE = "fr-FR-RemyMultilingualNeural"
EDGE_TTS_RATE = "+0%"
EDGE_TTS_PITCH = "+0Hz"

# --- SEGMENTS DE VOIX OFF (script de la démo) ---
# "00_value_prop" couvre le schéma d'intro (capture_intro()) — ce qui se passe à
# l'écran pendant ce segment (navigation initiale, silencieuse) n'apparaît jamais dans
# la vidéo finale, exactement comme la page de garde recouvrait la connexion sur
# l'ancien projet (cf. assemble()).
script_segments = [
    {
        "id": "00_value_prop",
        "text": (
            "Toutes vos factures fournisseur ne sont pas traitées dans la même application de gestion ? Multiplier les adresses de facturation électroniques dans l'annuaire public peut perturber vos fournisseurs et conduire à des erreurs de routage pénibles à résoudre. i-iinvoïcing routeur masque cette complexité : vos fournisseurs ne voient qu'une seule adresse de facturation électronique par entreprise , quel que soit le nombre d'applications en aval. Vous pouvez ainsi réorganiser vos flux interne en toute autonomie."
        ),
    },
    {
        "id": "01_companies",
        "text": (
            "Dans i-iinvoïcing routeur, chaque entreprise gérée dispose d'une fiche unique : SIREN, raison sociale, et ses "
            "identifiants d'accès à la plateforme agréée."
        ),
    },
    {
        "id": "02_target_applications",
        "text": (
            "On configure ensuite les canaux de sortie : une adresse mail pour Spènne-desk ou le "
            "comptable, ou une mise à disposition via l'API normalisée AFNOR pour un ERP comme Odoo — chacun "
            "avec ses propres identifiants. Connecté via l'API normalisée AFNOR, Odoo peut également envoyer ses factures client, suivre "
            "leur cycle de vie, transmettre de l'i-reporting et consulter l'annuaire, exactement comme s'il "
            "était branché directement sur la plateforme agréée."
        ),
    },
    {
        "id": "03_routing_rules",
        "text": (
            "Il ne reste qu'à décider, pour chaque fournisseur, vers quelles applications cibles "
            "router ses factures : la matrice croise fournisseurs et applications. Vous êtes notifié par mail lors de l'arrivée de la première facture d'un fournisseur, pour indiquer vers quelles applications la router."
        ),
    },
    {
        "id": "04_invoices",
        "text": (
            "Les factures reçues depuis la plateforme agréée sont automatiquement routées "
            "vers les bonnes cibles — consultables, filtrables, téléchargeables, avec le détail complet "
            "de leurs métadonnées issue de l'API normalisée AFNOR."
        ),
    },
    {
        "id": "05_lifecycle",
        "text": (
            "Un événement de cycle de vie — approbation, litige, paiement — peut être saisi "
            "manuellement à tout moment et vient enrichir l'historique de la facture."
        ),
    },
    {
        "id": "06_failed_routings",
        "text": (
            "En cas d'échec d'envoi, le routeur retente automatiquement plusieurs fois avant "
            "d'alerter les gestionnaires de facturation ; un cycle d'envoi peut aussi être forcé "
            "manuellement."
        ),
    },
    {
        "id": "07_traces",
        "text": (
            "Chaque échange avec la plateforme agréée est tracé en base, avec un identifiant de "
            "corrélation commun de bout en bout, pour un audit complet."
        ),
    },
    {
        "id": "08_access_audit",
        "text": (
            "Les accès à l'IHM sont restreints par entreprise et par rôle, et chaque action "
            "utilisateur — connexion, téléchargement, modification — est journalisée."
        ),
    },
    {
        "id": "09_outro",
        "text": (
            "Factures, routage, traces : tout reste consultable au même endroit. "
            "i-iinvoïcing routeur, une seule porte d'entrée pour vos factures."
        ),
    },
]


# --- SERVICES ---
def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def kill_stale_demo_services():
    """Tue tout ce qui écoute déjà sur DEMO_BACKEND_PORT/DEMO_FRONTEND_PORT avant de démarrer.

    `wait_for_service()` ci-dessous se contente de vérifier qu'un port est déjà ouvert pour
    décider de NE PAS relancer le service — pratique pour itérer vite sur ce script, mais un
    piège découvert en testant : un backend jetable resté ouvert depuis une exécution
    PRÉCÉDENTE (donc démarré avec une ancienne config, ex. ROUTER_OIDC_MODE=disabled avant que
    ce script passe à ROUTER_OIDC_MODE=dev pour la connexion admin simulée, § capture()) est
    réutilisé tel quel — la capture échoue alors en silence sur `/api/ihm/auth/login`
    (`404 {"detail": "Authentication is disabled"}`) sans que rien n'indique que le backend
    réutilisé date d'une autre version du script. Seuls DEMO_BACKEND_PORT/DEMO_FRONTEND_PORT
    sont ciblés (jamais un port arbitraire) : ce sont les deux seuls ports que ce script lui-même
    fait écouter, jamais ceux d'une instance de dev/prod réelle (cf. le commentaire sur ces
    constantes)."""
    for port in (DEMO_BACKEND_PORT, DEMO_FRONTEND_PORT):
        if is_port_open(port):
            print(f"🔪 Port {port} déjà occupé (exécution précédente ?) — arrêt du processus...")
            subprocess.run(["fuser", "-k", f"{port}/tcp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 10
    while time.time() < deadline and (is_port_open(DEMO_BACKEND_PORT) or is_port_open(DEMO_FRONTEND_PORT)):
        time.sleep(0.5)


def write_vite_proxy_config():
    """Le frontend appelle l'API en chemin relatif (`API_BASE = import.meta.env.VITE_API_BASE_URL
    ?? ''`, cf. frontend/src/api/http.ts — pensé pour Caddy en prod). En dev, il faut donc un
    proxy `/api` -> backend de démo ; ce fichier de config Vite dédié est généré ici et supprimé
    en fin d'exécution (cf. main()), pour ne rien laisser de permanent dans le dépôt."""
    VITE_PROXY_CONFIG.write_text(
        "import vue from '@vitejs/plugin-vue'\n"
        "import { defineConfig } from 'vite'\n\n"
        "export default defineConfig({\n"
        "  plugins: [vue()],\n"
        "  server: {\n"
        f"    proxy: {{ '/api': {{ target: '{BACKEND_URL}', changeOrigin: true }} }},\n"
        "  },\n"
        "})\n",
        encoding="utf-8",
    )


def wait_for_service(service_config):
    import requests
    name = service_config["name"]
    port = service_config["port"]
    url = service_config.get("check_url")

    print(f"⏳ Attente de {name} sur le port {port}...")
    for i in range(60):
        if is_port_open(port):
            if url:
                try:
                    resp = requests.get(url, timeout=2)
                    if resp.status_code < 500:
                        print(f"  ✅ {name} opérationnel.")
                        return True
                except Exception:
                    pass
            else:
                print(f"  ✅ {name} (port ouvert).")
                return True

        if i == 0:
            print(f"🚀 Lancement de {name}...")
            subprocess.Popen(
                service_config["cmd"],
                cwd=str(service_config["cwd"]),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        time.sleep(3)
    return False


# --- AUDIO (edge-tts, voix neuronale Microsoft Azure — gratuit, non officiel, pas de clonage) ---
async def generate_audio():
    print(f"🎙️ Phase Audio edge-tts (voix {EDGE_TTS_VOICE}, rate {EDGE_TTS_RATE}, pitch {EDGE_TTS_PITCH})...")
    try:
        import edge_tts
    except Exception as e:
        print(f"  ❌ Erreur import edge-tts : {e}")
        print("     -> pip install edge-tts")
        return {s['id']: 5.0 for s in script_segments}, {}

    durations = {}
    paths_map = {}
    for segment in script_segments:
        cache_key = f"{segment['text']}|{EDGE_TTS_VOICE}|{EDGE_TTS_RATE}|{EDGE_TTS_PITCH}"
        text_hash = hashlib.md5(cache_key.encode()).hexdigest()
        path = AUDIO_DIR / f"{segment['id']}_{text_hash}.mp3"

        for old_file in AUDIO_DIR.glob(f"{segment['id']}_*.mp3"):
            if old_file.name != path.name:
                old_file.unlink()

        if path.exists() and path.stat().st_size > 0:
            try:
                clip = mp.AudioFileClip(str(path))
                durations[segment['id']] = clip.duration
                clip.close()
                paths_map[segment['id']] = path
                print(f"  ✅ {segment['id']} (cache : {durations[segment['id']]:.1f}s)")
                continue
            except Exception:
                pass

        print(f"  🎙️ Génération {segment['id']} (nouveau texte détecté)...")
        try:
            communicate = edge_tts.Communicate(
                segment['text'], voice=EDGE_TTS_VOICE, rate=EDGE_TTS_RATE, pitch=EDGE_TTS_PITCH,
            )
            await communicate.save(str(path))
            clip = mp.AudioFileClip(str(path))
            durations[segment['id']] = clip.duration
            clip.close()
            paths_map[segment['id']] = path
            print(f"    -> OK ({durations[segment['id']]:.1f}s)")
        except Exception as e:
            print(f"    ❌ Échec (vérifier l'accès réseau, endpoint Microsoft non officiel) : {e}")
            durations[segment['id']] = 5.0
    return durations, paths_map


# --- UTILITAIRES CAPTURE ---
async def install_cursor(page):
    js_code = """
    window.setupFakeCursor = function() {
        if (document.getElementById('fake-cursor')) return;
        const cursor = document.createElement('div');
        cursor.id = 'fake-cursor';
        cursor.style.position = 'absolute';
        cursor.style.zIndex = '99999';
        cursor.style.width = '20px';
        cursor.style.height = '20px';
        cursor.style.borderRadius = '50%';
        cursor.style.backgroundColor = 'red';
        cursor.style.border = '2px solid white';
        cursor.style.pointerEvents = 'none';
        cursor.style.transition = 'all 0.5s ease-out';
        cursor.style.boxShadow = '0 0 10px rgba(0,0,0,0.5)';
        cursor.style.left = '0px';
        cursor.style.top = '0px';
        document.body.appendChild(cursor);

        window.moveCursor = (x, y) => {
          cursor.style.left = (x - 10) + 'px';
          cursor.style.top = (y - 10) + 'px';
        };

        window.clickCursor = () => {
          cursor.style.transform = 'scale(0.8)';
          cursor.style.backgroundColor = 'orange';
          setTimeout(() => {
            cursor.style.transform = 'scale(1)';
            cursor.style.backgroundColor = 'red';
          }, 200);
        };
    };
    window.setupFakeCursor();
    """
    await page.add_init_script(js_code)
    try:
        await page.evaluate(js_code)
    except Exception:
        pass


async def move_cursor_to_locator(page, locator):
    await page.evaluate("if(window.setupFakeCursor) window.setupFakeCursor();")
    try:
        box = await locator.bounding_box()
        if box:
            x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
            await page.evaluate(f"if(window.moveCursor) window.moveCursor({x}, {y})")
            await asyncio.sleep(0.6)
    except Exception:
        pass


async def click_with_cursor(page, locator, timeout=5000):
    """Déplace le curseur visible vers `locator`, l'anime au clic, puis clique réellement."""
    await locator.first.wait_for(state="visible", timeout=timeout)
    await move_cursor_to_locator(page, locator.first)
    try:
        await page.evaluate("if(window.clickCursor) window.clickCursor()")
    except Exception:
        pass
    await locator.first.click(timeout=timeout)


async def open_nav(page, nav_label, group_toggle_testid=None):
    """Navigue vers une page via un clic réel sur le menu latéral (App.vue) — ouvre le
    groupe "Paramétrage"/"Traces & journaux" si nécessaire (data-testid nav-settings-toggle /
    nav-traces-toggle) plutôt que de naviguer directement par URL, pour un rendu fidèle à
    l'usage réel."""
    link = page.get_by_role("link", name=nav_label, exact=True)
    if group_toggle_testid and (await link.count() == 0 or not await link.first.is_visible()):
        await click_with_cursor(page, page.locator(f'[data-testid="{group_toggle_testid}"]'))
        await asyncio.sleep(0.4)
        link = page.get_by_role("link", name=nav_label, exact=True)
    await click_with_cursor(page, link)
    await asyncio.sleep(0.6)


async def confirm_dialog(page, reroute_existing=None):
    """Valide la popin de confirmation (ConfirmDialog.vue), utilisée notamment par la
    matrice de règles de routage (data-testid confirm-dialog / confirm-dialog-confirm)."""
    dialog = page.locator('[data-testid="confirm-dialog"]')
    await dialog.wait_for(state="visible", timeout=5000)
    if reroute_existing is not None:
        radio_testid = "reroute-choice-existing" if reroute_existing else "reroute-choice-future-only"
        radio = page.locator(f'[data-testid="{radio_testid}"]')
        if await radio.count() > 0:
            await radio.check()
            await asyncio.sleep(0.3)
    # Laisse le temps de lire le contenu de la popin (titre + message + détail, § ConfirmDialog.vue)
    # avant de cliquer sur "Confirmer" — sans cette pause, la popin apparaît et disparaît trop vite
    # pour un spectateur de la vidéo.
    await asyncio.sleep(1.5)
    await click_with_cursor(page, page.locator('[data-testid="confirm-dialog-confirm"]'))
    await dialog.wait_for(state="detached", timeout=5000)


async def check_routing_cell(page, partner_text, target_name, reroute_existing=True):
    """Coche la case de la matrice de règles de routage pour la ligne dont le texte contient
    `partner_text` (SIREN ou raison sociale) et la colonne dont l'en-tête contient
    `target_name` — évite d'avoir à connaître les identifiants de base de données des lignes
    créées pendant la capture."""
    table = page.locator('[data-testid="routing-rules-list"]')
    # Les colonnes (une par application cible) sont peuplées par un appel asynchrone séparé de
    # celui qui affiche le tableau lui-même — attendre l'en-tête cherché explicitement plutôt que
    # de lire `thead th` une seule fois évite une lecture prématurée (0 colonne encore chargée),
    # piège découvert en testant ce script.
    await table.locator("thead th", has_text=target_name).first.wait_for(state="visible", timeout=8000)
    headers = table.locator("thead th")
    col_index = None
    # `has_text` ci-dessus fait une comparaison insensible à la casse (piège découvert en testant
    # ce script : les <th> de ce tableau sont rendus en CAPITALES par une règle CSS globale,
    # `text-transform: uppercase` sur `th`, cf. frontend/src/style.css — Playwright `inner_text()`
    # reflète le texte RENDU, donc une comparaison Python sensible à la casse comme
    # `target_name in header_text` échoue toujours ici, alors que `has_text` juste au-dessus,
    # insensible à la casse, avait bien trouvé la colonne).
    target_lower = target_name.lower()
    for i in range(1, await headers.count()):
        if target_lower in (await headers.nth(i).inner_text()).lower():
            col_index = i
            break
    if col_index is None:
        raise RuntimeError(f"Colonne '{target_name}' introuvable dans la matrice de routage")
    row = table.locator("tbody tr", has_text=partner_text)
    checkbox = row.locator("td").nth(col_index).locator('input[type="checkbox"]')
    await click_with_cursor(page, checkbox)
    await confirm_dialog(page, reroute_existing=reroute_existing)


# --- CAPTURE ---
async def capture(durations):
    print(f"🎥 Phase Capture Vidéo (Playwright) — cible : {BASE_URL}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            record_video_dir=str(VIDEO_DIR),
            viewport={'width': VIDEO_WIDTH, 'height': VIDEO_HEIGHT},
            record_video_size={'width': VIDEO_WIDTH, 'height': VIDEO_HEIGHT}
        )
        page = await context.new_page()
        await install_cursor(page)

        start_capture_time = time.time()

        def get_v_time():
            return time.time() - start_capture_time

        class SyncNarrator:
            def __init__(self, durations, time_func):
                self.durations = durations
                self.get_v_time = time_func
                self.current_id = None
                self.start_v_time = 0
                self.timestamps = {}

            async def start(self, segment_id):
                if self.current_id:
                    raise RuntimeError(
                        f"❌ ERREUR SYNCHRO : '{segment_id}' démarré alors que "
                        f"'{self.current_id}' est encore en cours."
                    )
                if segment_id not in self.durations:
                    print(f"⚠️  Attention : ID audio '{segment_id}' inconnu.")
                    return
                self.current_id = segment_id
                self.start_v_time = self.get_v_time()
                self.timestamps[segment_id] = self.start_v_time
                print(f"🎙️ [Sync Start] {segment_id} à {self.start_v_time:.1f}s")

            async def end(self, padding=0.5):
                if not self.current_id:
                    return
                duration = self.durations.get(self.current_id, 5.0)
                target_end = self.start_v_time + duration + padding
                now = self.get_v_time()
                if now < target_end:
                    print(f"⏳ [Sync Wait] Pause de {target_end - now:.1f}s pour finir '{self.current_id}'...")
                    while self.get_v_time() < target_end:
                        await asyncio.sleep(0.1)
                else:
                    print(f"✅ [Sync OK] '{self.current_id}' terminé avant la fin de l'action.")
                self.current_id = None

        narrator = SyncNarrator(durations, get_v_time)
        page.on("dialog", lambda dialog: print(f"💬 Dialogue : {dialog.message}") or asyncio.create_task(dialog.accept()))

        start_capture_time = time.time()

        try:
            # --- 00. Connexion + proposition de valeur (recouvertes par le schéma d'intro,
            #     cf. assemble()) ---
            # Connexion admin simulée (ROUTER_OIDC_MODE=dev, § NF3, DEMO_ADMIN_EMAIL/NAME
            # ci-dessus — même compte que le seed HTTP de seed_demo_data.py) : navigue
            # directement vers `/api/ihm/auth/login` au travers du proxy Vite de la démo
            # (`{BASE_URL}/api/...`, PAS `{BACKEND_URL}/...` directement) pour que le cookie
            # de session posé par la redirection soit bien associé à l'origine du frontend
            # (celle que le navigateur utilise ensuite pour tous ses appels `/api/...`) —
            # piège découvert en testant ce script : un login résolu directement contre
            # BACKEND_URL pose le cookie sur le mauvais port, invisible du frontend.
            await narrator.start("00_value_prop")
            print("🎬 Connexion admin + navigation vers l'IHM (silencieux, recouvert par le schéma d'intro)")
            login_url = (
                f"{BASE_URL}/api/ihm/auth/login?"
                f"email={urllib.parse.quote(DEMO_ADMIN_EMAIL)}&name={urllib.parse.quote(DEMO_ADMIN_NAME)}"
                "&next=%2Fcompanies"
            )
            try:
                await page.goto(login_url, wait_until="load", timeout=30000)
                await page.wait_for_selector(".sidebar", timeout=15000)
                print(f"  ✅ IHM chargée, connecté en tant que {DEMO_ADMIN_NAME}")
            except Exception as e:
                print(f"  ⚠️  Connexion/navigation initiale : {e}")
            await narrator.end(padding=1.0)

            # --- 01. Entreprises ---
            await narrator.start("01_companies")
            print("🎬 Entreprises — création d'une fiche entreprise")
            company_siren = "123456782"  # SIREN valide (clé de contrôle Luhn correcte)
            company_name = "Ma Société Demo"
            try:
                await open_nav(page, "Entreprises", group_toggle_testid="nav-settings-toggle")
                await page.fill('[data-testid="siren-input"]', company_siren)
                await page.fill('[data-testid="name-input"]', company_name)
                await click_with_cursor(page, page.locator('[data-testid="submit-button"]'))
                await page.wait_for_selector('[data-testid="companies-list"]', timeout=8000)
                print("  ✅ Entreprise créée")
                # Ouvre le formulaire d'identifiants SuperPDP (sans les soumettre — un test de
                # connexion réel échouerait sans plateforme certifiée jointe) pour montrer le champ.
                toggle = page.locator('[data-testid^="certified-platform-credentials-toggle-"]').first
                if await toggle.count() > 0:
                    await click_with_cursor(page, toggle)
                    await asyncio.sleep(1.2)
            except Exception as e:
                print(f"  ⚠️  Entreprises : {e}")
            await narrator.end(padding=1.0)

            # --- 02. Applications cibles (AFNOR API uniquement — "Spendesk" existe déjà
            #     dans la base de démo, § seed_demo_data.py, pas besoin de la recréer ici) ---
            await narrator.start("02_target_applications")
            print("🎬 Applications cibles — création d'une cible AFNOR API")
            try:
                await open_nav(page, "Applications cibles", group_toggle_testid="nav-settings-toggle")
                # Le formulaire démarre en méthode "mail" par défaut (TargetApplicationFormFields) —
                # bascule d'abord sur "afnor_api" AVANT de remplir le nom : changer
                # `ta-method-select` réinitialise TOUT `formState` côté Vue, y compris le champ
                # `name` — piège découvert en testant ce script (le remplir avant le changement de
                # méthode le faisait silencieusement effacer, d'où un `required` HTML resté vide et
                # un timeout sur le panneau d'identifiants qui suivait).
                await page.select_option('[data-testid="ta-method-select"]', "afnor_api")
                # Attend le rendu effectif des champs propres à afnor_api (TargetApplicationFormFields
                # bascule sur un `v-if` piloté par routingMethod) avant de continuer, plutôt qu'un
                # sleep() arbitraire — un délai fixe s'est révélé parfois insuffisant en testant ce
                # script (soumission avec l'ancien jeu de champs encore affiché, échec silencieux).
                await page.wait_for_selector('[data-testid="ta-app-type-select"]', timeout=5000)
                await page.fill('[data-testid="ta-name-input"]', "Odoo")
                await page.locator('[data-testid="ta-company-select"]').select_option(label=company_name)
                await click_with_cursor(page, page.locator('[data-testid="ta-submit-button"]'))
                # 20s (plutôt que 12s) : marge pour l'enregistrement vidéo Playwright + la liste
                # d'applications cibles désormais bien plus longue (seed_demo_data.py), qui
                # ralentissent le rendu par rapport à une page vierge.
                await page.wait_for_selector('[data-testid="ta-oauth-credentials"]', timeout=20000)
                print("  ✅ Application cible AFNOR API créée (Odoo), identifiants affichés")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  ⚠️  Application cible AFNOR API : {e}")
            await narrator.end(padding=1.0)

            # --- 03. Règles de routage ---
            partner_siren = "100000009"  # SIREN valide (clé de contrôle Luhn correcte)
            partner_name = "Fournisseur Demo"
            await narrator.start("03_routing_rules")
            print("🎬 Règles de routage — ajout d'un fournisseur, activation vers Odoo")
            try:
                await open_nav(page, "Règles de routage")
                await page.fill('[data-testid="partner-siren-input"]', partner_siren)
                await page.fill('[data-testid="partner-name-input"]', partner_name)
                await click_with_cursor(page, page.locator('[data-testid="partner-submit-button"]'))
                await page.wait_for_selector('[data-testid="routing-rules-list"]', timeout=8000)
                await check_routing_cell(page, partner_siren, "Odoo", reroute_existing=True)
                print("  ✅ Règle de routage activée (fournisseur -> Odoo)")
            except Exception as e:
                print(f"  ⚠️  Règles de routage : {e}")
            await narrator.end(padding=1.0)

            # --- 04. Factures reçues ---
            invoice_number = "FAC-DEMO-001"
            await narrator.start("04_invoices")
            print("🎬 Factures — simulation d'une réception, consultation du détail")
            try:
                companies_resp = await page.request.get(f"{BASE_URL}/api/ihm/companies")
                companies_list = await companies_resp.json()
                company = next(c for c in companies_list if c["siren"] == company_siren)
                await page.request.post(
                    f"{BASE_URL}/api/test/invoices/simulate",
                    data={
                        "company_id": company["id"],
                        "emitter_siren": partner_siren,
                        "emitter_name": partner_name,
                        "invoice_number": invoice_number,
                        "invoice_date": datetime.now().strftime("%Y-%m-%d"),
                        "amount_total": 1200.0,
                        "amount_excl_tax": 1000.0,
                    },
                )
                await open_nav(page, "Factures")
                row = page.locator(f'[data-testid="invoice-row-{invoice_number}"]')
                await row.wait_for(state="visible", timeout=8000)
                await click_with_cursor(page, row)
                await page.wait_for_selector('[data-testid="invoice-detail"]', timeout=8000)
                print("  ✅ Facture reçue, routée et affichée")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  ⚠️  Factures : {e}")
            await narrator.end(padding=1.0)

            # --- 05. Cycle de vie ---
            await narrator.start("05_lifecycle")
            print("🎬 Facture — saisie d'un événement de cycle de vie")
            try:
                await page.select_option('[data-testid="lifecycle-status-select"]', "approved")
                await click_with_cursor(page, page.locator('[data-testid="lifecycle-submit-button"]'))
                await page.wait_for_selector('[data-testid="lifecycle-events-list"]', timeout=8000)
                print("  ✅ Événement de cycle de vie enregistré")
                await asyncio.sleep(1.2)
            except Exception as e:
                print(f"  ⚠️  Cycle de vie : {e}")
            await narrator.end(padding=1.0)

            # --- 06. Échecs de routage ---
            await narrator.start("06_failed_routings")
            print("🎬 Échecs de routage — forcer un cycle d'envoi")
            try:
                await open_nav(page, "Échecs de routage")
                await click_with_cursor(page, page.locator('[data-testid="force-send-cycle-button"]'))
                await asyncio.sleep(1.5)
                print("  ✅ Cycle d'envoi forcé")
            except Exception as e:
                print(f"  ⚠️  Échecs de routage : {e}")
            await narrator.end(padding=1.0)

            # --- 07. Traces techniques ---
            await narrator.start("07_traces")
            print("🎬 Traces & journaux — traces techniques (FlowTrace)")
            try:
                await open_nav(page, "Traces techniques", group_toggle_testid="nav-traces-toggle")
                await page.wait_for_selector('[data-testid="flow-traces-table"]', timeout=8000)
                toggle = page.locator('[data-testid^="flow-trace-toggle-"]').first
                if await toggle.count() > 0:
                    await click_with_cursor(page, toggle)
                    await asyncio.sleep(1.2)
                print("  ✅ Détail d'une trace technique affiché")
            except Exception as e:
                print(f"  ⚠️  Traces techniques : {e}")
            await narrator.end(padding=1.0)

            # --- 08. Accès & audit ---
            await narrator.start("08_access_audit")
            print("🎬 Traces & journaux — gestion des accès puis journal d'audit")
            try:
                await open_nav(page, "Gestion des accès", group_toggle_testid="nav-settings-toggle")
                await page.wait_for_selector('[data-testid="users-table"]', timeout=8000)
                await asyncio.sleep(1.2)
            except Exception as e:
                print(f"  ⚠️  Gestion des accès : {e}")
            try:
                await open_nav(page, "Journal d'audit", group_toggle_testid="nav-traces-toggle")
                await page.wait_for_selector('[data-testid="audit-logs-table"]', timeout=8000)
                print("  ✅ Journal d'audit affiché")
                await asyncio.sleep(1.2)
            except Exception as e:
                print(f"  ⚠️  Journal d'audit : {e}")
            await narrator.end(padding=1.0)

            # --- 09. Conclusion ---
            await narrator.start("09_outro")
            print("🎬 Retour à la vue Factures pour la conclusion")
            try:
                await open_nav(page, "Factures")
                await asyncio.sleep(2.0)
            except Exception as e:
                print(f"  ⚠️  Conclusion : {e}")
            await narrator.end(padding=1.5)

        except Exception as e:
            print(f"  ❌ Erreur critique pendant la capture : {e}")

        await context.close()
        video_path = await page.video.path()
        return video_path, narrator.timestamps


# --- SCHÉMA D'INTRO (capture Playwright de artifacts/demo_intro_animation.html) ---
async def capture_intro(duration):
    """Capture l'animation d'intro comme un second mini-`capture()` : ouvre
    INTRO_HTML_PATH dans un vrai navigateur Playwright (mêmes polices Google Fonts,
    mêmes transitions CSS que ce que voit un humain qui ouvre le fichier), laisse le
    storyboard se jouer pendant `duration`, puis retourne le chemin de la vidéo
    enregistrée — remplace l'ancien diaporama PIL statique (create_intro_sequence),
    qui ne montrait qu'un instantané figé de chaque étape plutôt que l'animation réelle
    (icônes, tracés de flèches, apparitions) telle que conçue dans le fichier HTML.

    Contrairement à capture() (parcours applicatif scripté), il n'y a rien à cliquer
    ici : demo_intro_animation.html se joue tout seul au chargement (cf. son propre
    script), donc cette fonction se contente d'attendre."""
    print(f"🎬 Capture du schéma d'intro HTML ({duration:.1f}s) — {INTRO_HTML_PATH.name}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            record_video_dir=str(VIDEO_DIR),
            viewport={'width': VIDEO_WIDTH, 'height': VIDEO_HEIGHT},
            record_video_size={'width': VIDEO_WIDTH, 'height': VIDEO_HEIGHT},
        )
        page = await context.new_page()
        await page.goto(INTRO_HTML_PATH.as_uri(), wait_until="load", timeout=15000)
        await asyncio.sleep(duration)
        await context.close()
        video_path = await page.video.path()
        print("  ✅ Schéma d'intro capturé")
        return video_path



# --- MONTAGE ---
def assemble(video_path, intro_video_path, durations, audio_paths, timestamps):
    print("🎬 Phase Montage Final...")
    if not os.path.exists(video_path):
        print("  ❌ Fichier vidéo source introuvable.")
        return
    if not intro_video_path or not os.path.exists(intro_video_path):
        print("  ❌ Fichier vidéo du schéma d'intro introuvable.")
        return

    full_video = mp.VideoFileClip(video_path)

    intro_audio_dur = durations.get("00_value_prop", 5.0)
    intro_total_dur = intro_audio_dur + 1.5
    # .with_duration() cale la capture (qui inclut un peu de temps de navigation avant que
    # asyncio.sleep(duration) ne démarre, cf. capture_intro()) sur la durée exacte attendue par
    # le montage — coupe le léger surplus plutôt que de risquer une vidéo plus courte que prévu.
    intro_clip = mp.VideoFileClip(intro_video_path).with_duration(intro_total_dur)

    rest_of_video = full_video.subclipped(intro_total_dur, full_video.duration)
    video = mp.concatenate_videoclips([intro_clip, rest_of_video])

    audio_clips = []
    last_audio_end = 0
    overlaps_detected = []

    for sid, t_start in timestamps.items():
        p = audio_paths.get(sid)
        if p and p.exists():
            if t_start < last_audio_end:
                drift = last_audio_end - t_start
                overlaps_detected.append(f"{sid} (décalé de {drift:.2f}s)")
                actual_start = last_audio_end
            else:
                actual_start = t_start

            print(f"  🔊 Calage {sid} à {actual_start:.1f}s")
            a_clip = mp.AudioFileClip(str(p)).with_start(actual_start)
            audio_clips.append(a_clip)
            last_audio_end = actual_start + a_clip.duration + 0.8

    if overlaps_detected:
        print("\n" + "!" * 60)
        print("⚠️  ALERTE SYNCHRO : Des chevauchements audio ont été évités !")
        for msg in overlaps_detected:
            print(f"   - {msg}")
        print("💡 Conseil : Augmentez les temps d'attente (asyncio.sleep) dans capture().")
        print("!" * 60 + "\n")

    if audio_clips:
        video_with_audio = video.with_audio(mp.CompositeAudioClip(audio_clips))
        if last_audio_end > video.duration:
            print(f"⚠️  ATTENTION : L'audio dépasse la vidéo de {last_audio_end - video.duration:.1f}s. Ajout d'un freeze frame.")
            last_frame = video.get_frame(video.duration - 0.05)
            freeze_duration = last_audio_end - video.duration + 1.0
            freeze_clip = mp.ImageClip(last_frame).with_duration(freeze_duration).with_start(video.duration)
            video = mp.CompositeVideoClip([video_with_audio, freeze_clip])
        else:
            video = video_with_audio

    out_name = f"DEMO_ROUTEUR_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    out = BASE_DIR / out_name
    print(f"💾 Génération de {out}...")
    video.write_videofile(str(out), codec="libx264", audio_codec="aac", fps=24)
    print(f"✨ TERMINÉ ! Fichier : {out}")


async def main():
    script_start_time = time.time()
    print("⏱️  Démarrage du script...")

    assemble_only = "--assemble-only" in sys.argv
    meta_path = BASE_DIR / "last_meta.json"

    if not assemble_only:
        kill_stale_demo_services()
        demo_seed.reset_demo_database(db_path=DEMO_DB_PATH, invoice_storage_root=DEMO_INVOICE_STORAGE_ROOT)
        write_vite_proxy_config()
        for svc in APP_SETTINGS["services"]:
            if not wait_for_service(svc):
                print(f"❌ {svc['name']} n'a pas démarré à temps.")
                return
        demo_seed.seed_demo_data(backend_url=BACKEND_URL, admin_email=DEMO_ADMIN_EMAIL, admin_name=DEMO_ADMIN_NAME)
        demo_seed.seed_technical_logs(
            backend_dir=BACKEND_DIR, db_path=DEMO_DB_PATH, invoice_storage_root=DEMO_INVOICE_STORAGE_ROOT
        )

    durations, audio_paths = await generate_audio()

    try:
        if assemble_only:
            if not meta_path.exists():
                print("  ❌ Aucun fichier 'last_meta.json' trouvé. Lancez une capture complète d'abord.")
                return

            print("⚡ Mode Montage Seul activé. Réutilisation de la dernière capture...")
            with open(meta_path, "r") as f:
                meta = json.load(f)
                t_marks = meta["timestamps"]
                v_path = meta.get("video_path")
                intro_v_path = meta.get("intro_video_path")

            if not v_path or not os.path.exists(v_path):
                webms = list(VIDEO_DIR.glob("*.webm"))
                if not webms:
                    print("  ❌ Aucune vidéo .webm trouvée dans temp_video/")
                    return
                v_path = str(max(webms, key=os.path.getmtime))
                print(f"  🎬 Vidéo détectée : {v_path}")

            if not intro_v_path or not os.path.exists(intro_v_path):
                # Contrairement à la capture applicative, pas de repli par glob ici (deux .webm
                # récents dans temp_video/ ne sont pas fiablement discernables) : le mode
                # "montage seul" ne relance pas Playwright, donc la capture d'intro doit déjà
                # avoir été enregistrée par une exécution complète précédente.
                print("  ❌ Aucune vidéo de schéma d'intro dans 'last_meta.json'. Lancez une capture complète d'abord.")
                return

            assemble(v_path, intro_v_path, durations, audio_paths, t_marks)
        else:
            try:
                v_path, t_marks = await capture(durations)
                if v_path:
                    intro_total_dur = durations.get("00_value_prop", 5.0) + 1.5
                    intro_v_path = await capture_intro(intro_total_dur)
                    with open(meta_path, "w") as f:
                        json.dump(
                            {"video_path": v_path, "intro_video_path": intro_v_path, "timestamps": t_marks},
                            f, indent=2,
                        )
                    assemble(v_path, intro_v_path, durations, audio_paths, t_marks)
            except Exception as e:
                print(f"❌ Échec global : {e}")
                import traceback
                traceback.print_exc()
    finally:
        # Nettoyage du fichier de config Vite jetable — jamais laissé dans le dépôt.
        if VITE_PROXY_CONFIG.exists():
            VITE_PROXY_CONFIG.unlink()

    elapsed_time = time.time() - script_start_time
    minutes, seconds = divmod(elapsed_time, 60)
    print("\n" + "=" * 60)
    print(f"✨ Script terminé en {int(minutes)}m {seconds:.1f}s ({elapsed_time:.1f}s total)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
