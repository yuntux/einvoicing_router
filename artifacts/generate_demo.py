"""
Script d'automatisation de démonstration vidéo - Projet Klepsydrix

Ce script permet de générer une vidéo de démonstration (environ 2min50-3min15 avec les 11
segments actuels — le format "1 à 2 minutes" visé au départ a été dépassé au fil des demandes
d'enrichissement du contenu) en combinant :
1. Narration audio (F5-TTS, clonage vocal local à partir d'une voix de référence, voir
   user_doc/demo_video/voice_ref/) — a remplacé Kokoro ONNX, dont la voix française sonnait
   trop artificielle (voix ff_siwis entraînée sur moins de 11h de français).
2. Capture vidéo automatisée (Playwright), pilotant le frontend Klepsydrix (Vue + Vite)
   connecté au backend FastAPI, sur la base de démonstration seedée par
   backend/app/core/init_demo.py
3. Montage automatique (MoviePy)

ETAPES DE LA PRODUCION APPUYEE SUR UN LLM :
--------------------------------------------
Pré-requis : l'application est développée, le jeu de données de démo existe
(base "timetable" seedée via `backend/.venv/bin/python -m backend.app.core.init_demo`),
la documentation du projet est rédigée (voir user_doc/chef_etablissement_doc.md).

1. Envoyer au LLM la documentation du projet : "J'ai construit une web app (frontend Vue +
backend FastAPI) qui permet de construire l'emploi du temps annuel d'un établissement scolaire.
Je veux générer une vidéo de démonstration de 1 à 2 minutes avec une voix off en français. Voici
la documentation du projet en PJ. Rédige moi le tableau de minutage de la démonstration avec les
3 colonnes suivantes : 1/ le minutage 2/ l'action à réaliser visuellement par l'utilisateur
3/ le texte de la voix off "

2. Envoyer au LLM le tableau de minutage généré par le LLM, ainsi que ce script,
et lui demander : "Voici le tableau de minutage, adapte le script python ci-joint
pour qu'il corresponde au tableau de minutage et aux actions à réaliser.
Les sélecteurs CSS doivent être des placeholder à remplacer par les vrais "clics" à
l'étape suivante."

3. Envoyer au LLM : "Voici le script de génération vidéo, ainsi que les fichiers Vue de
l'application ciblée par la démo (ou le script frontend/scripts/doc-screenshots/lib.mjs
qui contient déjà les sélecteurs vérifiés). Adapte le script pour intégrer les sélecteurs
CSS et les actions à réaliser."

INSTALLATION DES DEPENDANCES :
------------------------------
# Dépendances système : ffmpeg (requis par MoviePy), polices DejaVu (page de garde)
sudo apt update && sudo apt install -y python3-pip python3-venv ffmpeg fonts-dejavu-core

# Dépendances Python. ATTENTION : torch par défaut sur PyPI peut résoudre vers une build CUDA
# (plusieurs Go de paquets nvidia-* inutiles sans GPU) — installer torch CPU-only d'abord :
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install --no-cache-dir playwright moviepy f5-tts huggingface_hub soundfile pillow requests --break-system-packages

# Navigateur Chromium pour Playwright + ses dépendances système
playwright install --with-deps chromium

# Voix de référence + checkpoint F5-TTS français : voir user_doc/demo_video/voice_ref/README.md
# pour la provenance de la voix (LibriVox, domaine public). Le checkpoint RASPIAUDIO
# (~1,35 Go, téléchargé automatiquement au premier lancement dans ~/.cache/huggingface) est sous
# licence CC-BY-NC-4.0 : USAGE NON COMMERCIAL UNIQUEMENT. Si la vidéo générée a un usage
# commercial, il faut soit obtenir une licence, soit utiliser un autre checkpoint/moteur.


EXECUTION DU SCRIPT :
---------------------
# Pré-requis : backend + frontend démarrés (./start_services.sh start) et base de démo seedée
python3 generate_demo.py

# Mode montage seul (réutilise la dernière capture vidéo, ne relance pas Playwright)
python3 generate_demo.py --assemble-only



STRUCTURE DU SCRIPT :
--------------------
- CONFIGURATION : URL locale du frontend Klepsydrix, identifiants du compte de démo
  (mêmes conventions que frontend/scripts/doc-screenshots/lib.mjs), réglages F5-TTS.
- AUDIO : Génération des segments WAV à partir du dictionnaire 'script_segments' via F5-TTS
          (clonage zero-shot de la voix de référence user_doc/demo_video/voice_ref/bernard_ref.wav,
          checkpoint français RASPIAUDIO/F5-French-MixedSpeakers-reduced). Lent sur CPU (environ
          5-6 minutes par segment, donc plus d'une heure pour les 11 segments à la première
          génération) — mis en cache par la suite (hash du texte), comme avec Kokoro.
- CAPTURE :
    - Injection d'un curseur rouge (JS) pour la visibilité des clics.
    - SyncNarrator : Classe assurant que l'audio et la vidéo restent synchronisés.
    - open_tree_path : portage Python de frontend/scripts/doc-screenshots/lib.mjs::openTreePath,
      pour naviguer dans l'arborescence de gauche (NotebooksTree.vue) par libellés affichés.
    - Logique métier : Parcours utilisateur automatisé dans Klepsydrix (connexion silencieuse,
      import STS-web/SIECLE, services prévisionnels + alignement + TRMD, contraintes enseignants,
      génération automatique des cours/groupes, placement automatique, attribution des salles,
      heatmap + glisser-déposer manuel, optimisation, export SIECLE, vue d'ensemble). Voir
      script_segments pour le détail exact de chaque étape.
- MONTAGE :
    - create_title_card : Génère une slide d'intro.
    - assemble : Assemble les clips et mixe l'audio en respectant les timestamps réels.

"""
import os
import asyncio
import time
import subprocess
import sys
import hashlib
import json
import socket
from datetime import datetime
from pathlib import Path

import moviepy as mp
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION GÉNÉRALE ---
BASE_DIR = Path(__file__).parent.absolute()
ROOT_DIR = BASE_DIR.parent
AUDIO_DIR = BASE_DIR / "temp_audio"
VIDEO_DIR = BASE_DIR / "temp_video"
AUDIO_DIR.mkdir(exist_ok=True)
VIDEO_DIR.mkdir(exist_ok=True)

BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"

# Klepsydrix est une app client-serveur (frontend Vite + backend FastAPI) : les deux services
# doivent tourner avant la capture. Mêmes conventions que start_services.sh et
# frontend/scripts/doc-screenshots/lib.mjs (BASE_URL, compte et base de démo).
BASE_URL = os.environ.get("KLEPSYDRIX_BASE_URL", "http://localhost:3000")
BACKEND_URL = "http://localhost:8000"
DEMO_DB = "timetable"
DEMO_IDENTIFIER = "demo@klepsydrix.fr"
DEMO_PASSWORD = "Demo1234!"

# Résolution de la capture Playwright (viewport, voir capture()) ET de la page de garde
# (create_title_card) : DOIVENT être identiques. MoviePy ne réconcilie pas silencieusement deux
# résolutions différentes lors de la concaténation — un décalage ici a produit un encodage corrompu
# (flash/strobe sur toute la vidéo montée, alors que la capture brute était propre) avant que ce
# soit repéré et corrigé.
VIDEO_WIDTH = 1440
VIDEO_HEIGHT = 900

# --- CONFIGURATION DE L'APPLICATION (page de garde) ---
APP_SETTINGS = {
    "title": "Klepsydrix",
    "subtitle": "L'emploi du temps annuel de l'établissement,\nconstruit et tenu à jour ensemble",
    "bg_color": (255, 255, 255),     # Blanc
    "accent_color": (99, 102, 241),  # Indigo #6366f1 (--accent-primary, frontend/src/assets/main.css)
    "footer_tagline": "Grille EDT • Classes • Enseignants • TRMD • Comptes & droits",
    # Backend FastAPI + frontend Vite à démarrer avant la capture (voir start_services.sh).
    "services": [
        {
            "name": "backend",
            "port": 8000,
            "check_url": f"{BACKEND_URL}/",
            "cmd": ["bash", "-c", f"PYTHONPATH={ROOT_DIR} {BACKEND_DIR}/.venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"],
            "cwd": ROOT_DIR,
        },
        {
            "name": "frontend",
            "port": 3000,
            "check_url": BASE_URL,
            "cmd": ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"],
            "cwd": FRONTEND_DIR,
        },
    ],
}

# --- CONFIGURATION F5-TTS (clonage vocal local) ---
# Architecture d'origine du modèle, PAS "F5TTS_v1_Base" : le checkpoint RASPIAUDIO a été
# entraîné dessus. Les deux configs ont les mêmes dimensions de tenseurs (1024/22/16) donc le
# chargement ne lève aucune erreur avec la mauvaise archi, mais des détails internes diffèrent
# (text_mask_padding, pe_attn_head) -> audio généré incompréhensible sans lever d'exception.
F5TTS_MODEL = "F5TTS_Base"
# Licence CC-BY-NC-4.0 (non-commercial) — voir INSTALLATION DES DEPENDANCES ci-dessus.
F5TTS_REPO_ID = "RASPIAUDIO/F5-French-MixedSpeakers-reduced"
F5TTS_CKPT_FILENAME = "model_last_reduced.pt"
F5TTS_VOCAB_FILENAME = "vocab.txt"
F5TTS_SEED = 42  # fixe, pour des générations reproductibles (changer si un artefact de liaison
                 # apparaît sur un segment : re-générer ce segment avec un autre seed suffit
                 # généralement, pas besoin de tout relancer).

VOICE_REF_DIR = BASE_DIR / "voice_ref"
VOICE_REF_AUDIO = VOICE_REF_DIR / "bernard_ref.wav"
VOICE_REF_TEXT_FILE = VOICE_REF_DIR / "bernard_ref.txt"

# --- SEGMENTS DE VOIX OFF (script de la démo) ---
# La connexion (compte de démo) n'a plus de segment narré dédié : elle est effectuée
# silencieusement pendant 01_intro, qui est de toute façon recouvert par la page de garde
# au montage (voir assemble()) — ce qui s'affiche à l'écran pendant ce segment n'apparaît
# jamais dans la vidéo finale.
script_segments = [
    {
        "id": "01_intro",
        "text": "Klepsydrix construit l'emploi du temps annuel d'un établissement, de la pré-rentrée jusqu'à la grille finale."
    },
    {
        "id": "02_import_siecle",
        "text": "Tout part de vos données STS-web et SIECLE : professeurs, matières, classes, élèves, responsables sont importés pour initialiser la base de données."
    },
    {
        "id": "03_services_trmd",
        "text": "Chaque service prévisionnel — classe, matière, professeur — peut être aligné entre classes ; le TRMD synthétise ensuite les besoins par discipline face aux moyens professeurs disponibles."
    },
    {
        "id": "04_teacher_constraints",
        "text": "L'utilisateur peut saisir les indisponibilités et préférences de créneaux de chaque enseignant dans une grille dédiée — même logique pour les classes et les autres ressources."
    },
    {
        "id": "05_generate_courses",
        "text": "Les cours et les groupes de spécialité sont ensuite générés automatiquement à partir de ces données."
    },
    {
        "id": "06_placement_auto",
        "text": "Le placement des cours est confié à Timefold, un moteur open source de résolution de contraintes, puissant et éprouvé."
    },
    {
        "id": "07_room_assignment",
        "text": "Chaque cours peut être restreint à un groupe de salles ; Klepsydrix attribue ensuite la salle précise selon les préférences des professeurs et des classes, la disponibilité, en minimisant les déplacements."
    },
    {
        "id": "08_heatmap_dragdrop",
        "text": "La carte de chaleur montre le score de chaque créneau ; et à tout moment, un cours peut être ajusté ou replacé à la main, d'un simple glisser-déposer."
    },
    {
        "id": "09_optimize",
        "text": "Un algorithme permet d'optimiser l'ensemble de l'emploi du temps afin de limiter les trous tout en maximisant les préférences facultatives."
    },
    {
        "id": "10_export_siecle",
        "text": "Une fois les groupes stabilisés, le rattachement élèves-groupes repart vers SIECLE en un clic."
    },
    {
        "id": "11_overview_outro",
        "text": "L'emploi du temps complet reste visible et modifiable à tout moment : Klepsydrix, l'emploi du temps annuel, piloté de bout en bout."
    },
]


# --- SERVICES ---
def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_service(service_config):
    import requests
    name = service_config["name"]
    port = service_config["port"]
    url = service_config.get("check_url")

    print(f"⏳ Attente de {name} sur le port {port}...")
    for i in range(40):
        if is_port_open(port):
            if url:
                try:
                    resp = requests.get(url, timeout=2)
                    if resp.status_code == 200:
                        print(f"  ✅ {name} opérationnel.")
                        return True
                except Exception:
                    pass
            else:
                print(f"  ✅ {name} (port ouvert).")
                return True

        if i % 5 == 0:
            print(f"🚀 [Tentative {i // 5 + 1}] Lancement de {name}...")
            subprocess.Popen(
                service_config["cmd"],
                cwd=str(service_config["cwd"]),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        time.sleep(3)
    return False


# --- AUDIO (F5-TTS, clonage vocal local à partir de voice_ref/) ---
def generate_audio():
    print("🎙️ Phase Audio F5-TTS (clonage vocal, voix FR RASPIAUDIO)...")
    try:
        from huggingface_hub import hf_hub_download
        from f5_tts.api import F5TTS
        import soundfile as sf
    except Exception as e:
        print(f"  ❌ Erreur import F5-TTS : {e}")
        print("     -> pip install f5-tts huggingface_hub soundfile")
        return {s['id']: 5.0 for s in script_segments}, {}

    if not VOICE_REF_AUDIO.exists() or not VOICE_REF_TEXT_FILE.exists():
        print(f"  ❌ Voix de référence introuvable : {VOICE_REF_AUDIO}")
        print(f"     -> voir {VOICE_REF_DIR / 'README.md'} pour la reconstituer")
        return {s['id']: 5.0 for s in script_segments}, {}
    ref_text = VOICE_REF_TEXT_FILE.read_text(encoding="utf-8").strip()

    durations = {}
    paths_map = {}

    # Si tous les segments sont déjà en cache, on évite de charger le modèle (téléchargement +
    # init coûteux) pour rien.
    pending = []
    for segment in script_segments:
        text_hash = hashlib.md5(segment['text'].encode()).hexdigest()
        path = AUDIO_DIR / f"{segment['id']}_{text_hash}.wav"

        # Nettoyage des anciens fichiers pour cet ID si le texte a changé
        for old_file in AUDIO_DIR.glob(f"{segment['id']}_*.wav"):
            if old_file.name != path.name:
                old_file.unlink()

        if path.exists() and path.stat().st_size > 0:
            try:
                info = sf.info(str(path))
                durations[segment['id']] = info.frames / info.samplerate
                paths_map[segment['id']] = path
                print(f"  ✅ {segment['id']} (cache : {durations[segment['id']]:.1f}s)")
                continue
            except Exception:
                pass
        pending.append((segment, path))

    if not pending:
        return durations, paths_map

    print(f"  ⏳ Chargement du modèle F5-TTS ({F5TTS_REPO_ID}, architecture {F5TTS_MODEL})...")
    ckpt = hf_hub_download(F5TTS_REPO_ID, F5TTS_CKPT_FILENAME)
    vocab = hf_hub_download(F5TTS_REPO_ID, F5TTS_VOCAB_FILENAME)
    f5tts = F5TTS(model=F5TTS_MODEL, ckpt_file=ckpt, vocab_file=vocab, device="cpu")
    print("  ✅ Modèle chargé.")

    for segment, path in pending:
        print(f"  🎙️ Génération {segment['id']} (nouveau texte détecté, ~5-6 min sur CPU)...")
        try:
            f5tts.infer(
                ref_file=str(VOICE_REF_AUDIO),
                ref_text=ref_text,
                gen_text=segment['text'],
                file_wave=str(path),
                seed=F5TTS_SEED,
            )
            info = sf.info(str(path))
            durations[segment['id']] = info.frames / info.samplerate
            paths_map[segment['id']] = path
            print(f"    -> OK ({durations[segment['id']]:.1f}s)")
        except Exception as e:
            print(f"    ❌ Échec : {e}")
            durations[segment['id']] = 5.0
    return durations, paths_map


# --- UTILITAIRES CAPTURE ---
async def install_cursor(page):
    """Injections du code JS pour le curseur (définition des fonctions et style)."""
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


async def move_cursor(page, selector=None, x=None, y=None):
    """Déplace le pointeur rouge vers un élément ou des coordonnées."""
    await page.evaluate("if(window.setupFakeCursor) window.setupFakeCursor();")

    if selector:
        try:
            box = await page.locator(selector).first.bounding_box()
            if box:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
        except Exception:
            pass

    if x is not None and y is not None:
        try:
            await page.evaluate(f"if(window.moveCursor) window.moveCursor({x}, {y})")
            await asyncio.sleep(0.6)
        except Exception:
            pass


async def move_cursor_to_locator(page, locator):
    """Déplace le curseur vers un Locator déjà résolu (utile après un .filter()/hasText)."""
    try:
        box = await locator.bounding_box()
        if box:
            await move_cursor(page, None, box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    except Exception:
        pass


async def close_modal(page):
    """Ferme une modale/popin ouverte. BaseModal.vue (wizards) N'A PAS de handler Escape — appuyer
    sur Echap est un no-op qui laisse la modale ouverte et bloque tous les clics suivants (piège
    découvert en testant ce script : une modale restée ouverte après 02_import_siecle a fait
    échouer les 8 segments suivants en timeout). Seuls un clic sur .btn-close (BaseModal, CoursePopin)
    ou en dehors de la modale la ferment. .btn-close est réutilisé tel quel dans les deux contextes,
    donc cibler la première instance visible suffit (une seule modale/popin ouverte à la fois)."""
    try:
        btn = page.locator(".btn-close").first
        if await btn.count() > 0:
            await btn.click(timeout=3000)
            await asyncio.sleep(0.3)
    except Exception:
        pass


async def stop_solver_if_running(page, timeout=2000, wait_gone_timeout=25000):
    """Arrête un calcul Timefold encore en cours (bouton 'Arrêter le calcul' de
    SolverProgressOverlay.vue). Sans ça, l'overlay plein écran reste affiché tant que le solveur
    tourne et bloque tous les clics des segments suivants (piège découvert en testant ce script :
    le solve d'optimisation, plus long, était encore actif quand le segment suivant a tenté de
    naviguer dans le menu — timeout 30s). close_modal() ne suffit pas ici : cet overlay n'a pas de
    .btn-close, seulement ce bouton dédié.

    L'arrêt est ASYNCHRONE côté backend (endpoint POST /api/timetable/stop, message "Résolution
    annulée" mais `terminate_early()` de Timefold met un moment à réellement s'arrêter — piège
    découvert lui aussi en testant : un clic sur "Arrêter le calcul" suivi d'une pause fixe de
    0.5s ne suffit pas, l'overlay reste affiché et bloque le segment suivant, voire fuit jusqu'à
    la PROCHAINE exécution du script si le processus se termine avant que le solve ait fini de
    s'arrêter côté serveur). On attend donc la disparition réelle de l'overlay plutôt qu'une pause
    fixe."""
    try:
        overlay = page.locator(".solver-overlay-fullscreen")
        if await overlay.count() > 0:
            stop_btn = page.get_by_text("Arrêter le calcul", exact=False).first
            if await stop_btn.count() > 0:
                await stop_btn.click(timeout=timeout)
            await overlay.wait_for(state="detached", timeout=wait_gone_timeout)
    except Exception:
        pass


async def submit_wizard_step(page, timeout=3000):
    """Clique le bouton de soumission de l'étape courante d'un GenericWizard (GenericForm.vue,
    bouton primary type=submit dans .form-actions ; réutilisé tel quel par le wizard). Best-effort
    seulement : si l'étape a des champs obligatoires non pré-remplis, le clic peut échouer côté
    validation front sans lever d'exception Playwright — dans ce cas la modale reste simplement
    affichée, ce qui est un repli visuel acceptable pour la démo. Retourne True si un clic a eu lieu."""
    try:
        btn = page.locator(".generic-wizard .form-actions button[type='submit']").first
        if await btn.count() > 0:
            await btn.click(timeout=timeout)
            return True
    except Exception:
        pass
    return False


async def open_tree_path(page, titles, animate=True):
    """Portage Python de frontend/scripts/doc-screenshots/lib.mjs::openTreePath.

    Ouvre un chemin dans l'arborescence de gauche (NotebooksTree.vue) par les libellés
    affichés, ex. open_tree_path(page, ["Emploi du temps", "Classes", "Liste"]).
    """
    l1_title = titles[0]
    l2_title = titles[1] if len(titles) > 1 else None
    l3_title = titles[2] if len(titles) > 2 else None

    l1_header = page.locator(".nav-group-header", has_text=l1_title).first
    await l1_header.wait_for(state="visible")
    if animate:
        await move_cursor_to_locator(page, l1_header)
        await page.evaluate("window.clickCursor()")
    l1_class = await l1_header.get_attribute("class") or ""
    if "open" not in l1_class:
        await l1_header.click()
    if not l2_title:
        return

    l1_submenu = l1_header.locator("xpath=following-sibling::*[1]")
    l2_header = l1_submenu.locator(".submenu-item", has_text=l2_title).first
    await l2_header.wait_for(state="visible")
    if animate:
        await move_cursor_to_locator(page, l2_header)
        await page.evaluate("window.clickCursor()")

    l2_class = await l2_header.get_attribute("class") or ""
    if "has-children" in l2_class:
        if "open" not in l2_class:
            await l2_header.click()
        if not l3_title:
            return
        l2_submenu = l2_header.locator("xpath=following-sibling::*[1]")
        l3_item = l2_submenu.locator(".sub-submenu-item", has_text=l3_title).first
        if animate:
            await move_cursor_to_locator(page, l3_item)
            await page.evaluate("window.clickCursor()")
        await l3_item.click()
    else:
        await l2_header.click()


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
            """Gère la synchronisation entre les actions de capture et la narration audio."""

            def __init__(self, durations, time_func):
                self.durations = durations
                self.get_v_time = time_func
                self.current_id = None
                self.start_v_time = 0
                self.timestamps = {}

            async def start(self, segment_id):
                if self.current_id:
                    raise RuntimeError(
                        f"❌ ERREUR SYNCHRO : Impossible de démarrer '{segment_id}' car "
                        f"'{self.current_id}' est encore en cours. Appelez .end() d'abord."
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
                    wait_time = target_end - now
                    print(f"⏳ [Sync Wait] Pause de {wait_time:.1f}s pour finir '{self.current_id}'...")
                    while self.get_v_time() < target_end:
                        await asyncio.sleep(0.1)
                else:
                    print(f"✅ [Sync OK] '{self.current_id}' terminé avant la fin de l'action.")
                self.current_id = None

        narrator = SyncNarrator(durations, get_v_time)
        page.on("dialog", lambda dialog: print(f"💬 Dialogue : {dialog.message}") or asyncio.create_task(dialog.accept()))

        start_capture_time = time.time()

        try:
            print("🎬 Navigation vers l'écran de connexion Klepsydrix...")
            await page.goto(f"{BASE_URL}/login?db={DEMO_DB}", wait_until="load", timeout=30000)
            try:
                await page.wait_for_selector("text=Connexion", timeout=15000)
            except Exception:
                pass

            # --- 01. Intro ---
            # Ce segment est recouvert par la page de garde au montage (voir assemble()) :
            # ce qui se passe ici à l'écran n'apparaît jamais dans la vidéo finale. C'est donc
            # ici, silencieusement, qu'on effectue la connexion (compte de démonstration).
            await narrator.start("01_intro")
            print("🎬 Connexion à Klepsydrix (silencieux, recouvert par la page de garde)")
            try:
                # Authentification réelle (API), mêmes conventions que
                # frontend/scripts/doc-screenshots/lib.mjs::loginAsDemo — plus fiable qu'une
                # saisie simulée dans le formulaire pour un script non-interactif.
                resp = await page.request.post(
                    f"{BASE_URL}/api/auth/login/local",
                    headers={"X-Klepsydrix-Database": DEMO_DB},
                    data={"identifier": DEMO_IDENTIFIER, "password": DEMO_PASSWORD},
                )
                if not resp.ok:
                    print(f"  ⚠️  Échec de connexion démo : {resp.status} {await resp.text()}")
                await context.add_cookies([{"name": "klepsydrix_db", "value": DEMO_DB, "url": BASE_URL}])

                await page.goto(BASE_URL, wait_until="load", timeout=30000)
                await page.wait_for_selector(".sidebar", timeout=15000)
                print("  ✅ Connecté, arrivée sur l'écran principal")
            except Exception as e:
                print(f"  ⚠️  Connexion : {e}")
            await narrator.end(padding=1.5)

            # --- 02. Import STS-web / SIECLE ---
            await narrator.start("02_import_siecle")
            print("🎬 Pré-rentrée — Importer un flux STS-web")
            try:
                await open_tree_path(page, ["Pré-rentrée", "Importer un flux STS-web"])
                await page.wait_for_selector(".generic-wizard", timeout=15000)
                print("  ✅ Wizard d'import STS-web affiché")
                await asyncio.sleep(2.5)
            except Exception as e:
                print(f"  ⚠️  Import STS-web : {e}")
            finally:
                # Fermeture systématique : une modale restée ouverte bloque tous les clics
                # des segments suivants (voir close_modal).
                await close_modal(page)
            await narrator.end(padding=1.0)

            # --- 03. Services par classe (+ alignement) puis TRMD ---
            await narrator.start("03_services_trmd")
            print("🎬 Pré-rentrée — Services par classe, puis TRMD")
            try:
                await open_tree_path(page, ["Pré-rentrée", "Services par classe"])
                await asyncio.sleep(0.8)
                # Sélectionne la première classe du panneau maître pour peupler le détail
                # (même logique que la sélection "6A" utilisée ailleurs).
                first_division_row = page.locator(".generic-list-row, tr, [class*='list-row']").first
                if await first_division_row.count() > 0:
                    await move_cursor_to_locator(page, first_division_row)
                    await first_division_row.click()
                print("  ✅ Services de la classe affichés")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  ⚠️  Services par classe : {e}")
            try:
                await open_tree_path(page, ["Pré-rentrée", "TRMD"])
                print("  ✅ Synthèse TRMD affichée")
                await asyncio.sleep(2.2)
            except Exception as e:
                print(f"  ⚠️  TRMD : {e}")
            await narrator.end(padding=1.0)

            # --- 04. Enseignants : vœux et contraintes ---
            await narrator.start("04_teacher_constraints")
            print("🎬 Enseignants — Vœux et contraintes")
            try:
                await open_tree_path(page, ["Emploi du temps", "Enseignants", "Vœux et contraintes"])
                await asyncio.sleep(0.8)
                # Sélectionne le premier enseignant du panneau maître pour afficher sa grille
                # de préférences (PreferenceGrid) plutôt que l'état vide.
                first_teacher_row = page.locator(".generic-list-row, tr, [class*='list-row']").first
                if await first_teacher_row.count() > 0:
                    await move_cursor_to_locator(page, first_teacher_row)
                    await first_teacher_row.click()
                    print("  ✅ Grille de préférences d'un enseignant affichée")
                await asyncio.sleep(1.8)
            except Exception as e:
                print(f"  ⚠️  Vœux et contraintes (enseignants) : {e}")
            await narrator.end(padding=1.0)

            # --- 05. Génération automatique des cours et groupes ---
            await narrator.start("05_generate_courses")
            print("🎬 Pré-rentrée — Générer les cours, puis les groupes de spécialité")
            try:
                await open_tree_path(page, ["Pré-rentrée", "Générer les cours"])
                await page.wait_for_selector(".generic-wizard", timeout=15000)
                await asyncio.sleep(1.5)
                print("  ✅ Wizard 'Générer les cours' affiché")
            except Exception as e:
                print(f"  ⚠️  Générer les cours : {e}")
            finally:
                await close_modal(page)
            try:
                await open_tree_path(page, ["Pré-rentrée", "Générer les groupes de spécialité"])
                await page.wait_for_selector(".generic-wizard", timeout=15000)
                await asyncio.sleep(1.5)
                print("  ✅ Wizard 'Générer les groupes de spécialité' affiché")
            except Exception as e:
                print(f"  ⚠️  Générer les groupes de spécialité : {e}")
            finally:
                await close_modal(page)
            await narrator.end(padding=1.0)

            # --- 06. Placement automatique (Timefold) ---
            await narrator.start("06_placement_auto")
            print("🎬 Emploi du temps — Placement automatique (Timefold)")
            try:
                await open_tree_path(page, ["Emploi du temps", "Placement automatique"])
                await page.wait_for_selector(".generic-wizard", timeout=15000)
                # Best-effort : tente de soumettre l'étape courante pour déclencher le calcul.
                # Peut échouer silencieusement si des champs obligatoires ne sont pas pré-remplis
                # (voir submit_wizard_step) — dans ce cas on montre simplement le wizard de config.
                await submit_wizard_step(page)
                try:
                    await page.wait_for_selector(".solver-overlay-fullscreen", timeout=12000)
                    print("  ✅ Overlay du solveur Timefold visible (placement)")
                    await asyncio.sleep(3)
                except Exception:
                    print("  ⚠️  Overlay solveur non atteint, wizard de config affiché à la place")
                    await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  ⚠️  Placement automatique : {e}")
            finally:
                await stop_solver_if_running(page)
                await close_modal(page)
            await narrator.end(padding=1.0)

            # --- 07. Groupe de salles sur un cours, puis attribution automatique ---
            await narrator.start("07_room_assignment")
            print("🎬 Fiche cours (groupe de salles), puis Attribuer les salles")
            try:
                # Retour explicite sur la grille EDT (écran d'accueil) : depuis l'étape 4, on est
                # resté sur "Enseignants > Vœux et contraintes", qui n'a pas de .placed-course — les
                # étapes 5-6 (actions de menu) ne changent pas la page affichée derrière leur wizard.
                await page.goto(BASE_URL, wait_until="load", timeout=15000)
                await page.wait_for_selector(".sidebar", timeout=10000)
            except Exception as e:
                print(f"  ⚠️  Retour à la grille : {e}")
            try:
                first_course_card = page.locator(".placed-course").first
                if await first_course_card.count() > 0:
                    await move_cursor_to_locator(page, first_course_card)
                    await first_course_card.dblclick()
                    await page.wait_for_selector("text=Salles", timeout=8000)
                    print("  ✅ Fiche cours ouverte, section Salles visible")
                    await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  ⚠️  Fiche cours (Salles) : {e}")
            finally:
                await close_modal(page)
            try:
                await open_tree_path(page, ["Emploi du temps", "Attribuer les salles"])
                await page.wait_for_selector(".generic-wizard", timeout=15000)
                await submit_wizard_step(page)
                try:
                    await page.wait_for_selector(".solver-overlay-fullscreen", timeout=12000)
                    print("  ✅ Overlay du solveur Timefold visible (salles)")
                    await asyncio.sleep(3)
                except Exception:
                    print("  ⚠️  Overlay solveur non atteint, wizard de config affiché à la place")
                    await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  ⚠️  Attribuer les salles : {e}")
            finally:
                await stop_solver_if_running(page)
                await close_modal(page)
            await narrator.end(padding=1.0)

            # --- 08. Placement assisté (heatmap) + ajustement manuel (drag & drop) ---
            await narrator.start("08_heatmap_dragdrop")
            print("🎬 Placement assisté (heatmap) puis glisser-déposer d'un cours")
            try:
                # Le <label>Placement assisté :</label> n'est pas cliquable pour basculer le
                # switch (piège découvert en testant : le clic "réussissait" sans lever d'erreur
                # mais le toggle restait sur "Désactivé"). BaseToggle.vue expose un span
                # .toggle-label-right (texte "Activé") qui force explicitement l'état ON — plus
                # fiable qu'un clic sur la checkbox elle-même, qui aurait juste basculé l'état
                # courant (pas idempotent).
                filter_item = page.locator(".filter-item", has_text="Placement assisté")
                heatmap_toggle_on = filter_item.locator(".toggle-label-right").first
                if await heatmap_toggle_on.count() > 0:
                    await move_cursor_to_locator(page, heatmap_toggle_on)
                    await heatmap_toggle_on.click()
                    print("  ✅ Toggle 'Placement assisté' activé")
                    await asyncio.sleep(0.5)
                course_card = page.locator(".placed-course").first
                if await course_card.count() > 0:
                    await move_cursor_to_locator(page, course_card)
                    await course_card.click()
                    await page.wait_for_selector(".heatmap-overlay", timeout=8000)
                    print("  ✅ Carte de chaleur affichée")
                await asyncio.sleep(1.8)
            except Exception as e:
                print(f"  ⚠️  Heatmap : {e}")
            try:
                source = page.locator(".placed-course").first
                target = page.locator(".heatmap-overlay, [class*='grid-cell']").first
                if await source.count() > 0 and await target.count() > 0:
                    await source.drag_to(target)
                    print("  ✅ Cours déplacé par glisser-déposer")
                await asyncio.sleep(1.2)
            except Exception as e:
                print(f"  ⚠️  Glisser-déposer : {e}")
            await narrator.end(padding=1.0)

            # --- 09. Optimiser l'emploi du temps ---
            await narrator.start("09_optimize")
            print("🎬 Emploi du temps — Optimiser l'emploi du temps (Timefold)")
            try:
                await open_tree_path(page, ["Emploi du temps", "Optimiser l'emploi du temps"])
                await page.wait_for_selector(".generic-wizard", timeout=15000)
                await submit_wizard_step(page)
                try:
                    await page.wait_for_selector(".solver-overlay-fullscreen", timeout=12000)
                    print("  ✅ Overlay du solveur Timefold visible (optimisation)")
                    await asyncio.sleep(3)
                except Exception:
                    print("  ⚠️  Overlay solveur non atteint, wizard de config affiché à la place")
                    await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  ⚠️  Optimiser l'emploi du temps : {e}")
            finally:
                await stop_solver_if_running(page)
                await close_modal(page)
            await narrator.end(padding=1.0)

            # --- 10. Export du rattachement élèves/groupes vers SIECLE ---
            await narrator.start("10_export_siecle")
            print("🎬 Pré-rentrée — Exporter le rattachement élèves/groupes vers SIECLE")
            try:
                await open_tree_path(page, ["Pré-rentrée", "Exporter le rattachement élèves/groupes vers SIECLE"])
                await page.wait_for_selector(".generic-wizard", timeout=15000)
                print("  ✅ Wizard d'export SIECLE affiché")
                await asyncio.sleep(2.5)
            except Exception as e:
                print(f"  ⚠️  Export SIECLE : {e}")
            finally:
                await close_modal(page)
            await narrator.end(padding=1.0)

            # --- 11. Vue d'ensemble de la grille finale, puis Outro ---
            await narrator.start("11_overview_outro")
            print("🎬 Vue d'ensemble de la grille de l'emploi du temps")
            try:
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(0.5)
                grid = page.locator(".grid-container, [id*='gantt'], [class*='timetable-grid']").first
                if await grid.count() > 0:
                    await page.evaluate(
                        "document.querySelector('.grid-container, [id*=gantt], [class*=timetable-grid]')"
                        " && document.querySelector('.grid-container, [id*=gantt], [class*=timetable-grid]').scrollBy(200, 0)"
                    )
                print("  ✅ Vue d'ensemble affichée")
                await asyncio.sleep(2)
            except Exception as e:
                print(f"  ⚠️  Vue d'ensemble : {e}")
            await narrator.end(padding=1.5)

        except Exception as e:
            print(f"  ❌ Erreur critique pendant la capture : {e}")

        await context.close()
        video_path = await page.video.path()
        return video_path, narrator.timestamps


def create_logo_image(size=200):
    """Crée le logo Klepsydrix (sablier blanc sur fond arrondi accent), fidèle à
    frontend/src/components/BaseLogo.vue."""
    img = Image.new('RGBA', (size, size), color=(0, 0, 0, 0))  # Transparent
    draw = ImageDraw.Draw(img)

    # Fond accent avec coins arrondis (rayon = 20% de la taille)
    radius = int(size * 0.2)
    accent = APP_SETTINGS["accent_color"]
    draw.rounded_rectangle(
        [(0, 0), (size, size)],
        radius=radius,
        fill=(accent[0], accent[1], accent[2], 255)
    )

    # Sablier blanc : barre haute, deux triangles se rejoignant au centre, barre basse
    # (approximation du path SVG de BaseLogo.vue : "M5 3h14M5 21h14M7 3v3a5 5..." sur un
    # viewBox 24x24).
    scale = size / 24.0
    x1, x2 = 6 * scale, 18 * scale
    y_top, y_bottom = 5 * scale, 19 * scale
    cx, cy = size / 2, size / 2
    bar_h = 1.6 * scale

    draw.rounded_rectangle([(x1, y_top - bar_h / 2), (x2, y_top + bar_h / 2)], radius=bar_h / 2, fill=(255, 255, 255, 255))
    draw.rounded_rectangle([(x1, y_bottom - bar_h / 2), (x2, y_bottom + bar_h / 2)], radius=bar_h / 2, fill=(255, 255, 255, 255))
    draw.polygon([(x1, y_top), (x2, y_top), (cx, cy)], fill=(255, 255, 255, 255))
    draw.polygon([(x1, y_bottom), (x2, y_bottom), (cx, cy)], fill=(255, 255, 255, 255))

    return img


def create_title_card(duration):
    """Génère la page de garde complète avec PIL + MoviePy, à la résolution EXACTE de la capture
    (VIDEO_WIDTH x VIDEO_HEIGHT) — voir le commentaire sur ces constantes : une page de garde à une
    résolution différente de la capture a produit un montage visuellement corrompu (flash/strobe)
    une fois concaténée par MoviePy, alors que chaque clip pris séparément était propre."""
    print(f"🎨 Création de la page de garde ({duration:.1f}s)...")

    W, H = VIDEO_WIDTH, VIDEO_HEIGHT
    # Mise à l'échelle de la mise en page (conçue à l'origine pour un canevas 1920x1080) au ratio
    # de la largeur réelle, plutôt que des coordonnées en dur — reste correct si VIDEO_WIDTH change.
    scale = W / 1920

    title_img = Image.new('RGB', (W, H), color=APP_SETTINGS["bg_color"])
    draw = ImageDraw.Draw(title_img)

    def scaled_font(path, fallback_path, base_size):
        size = max(8, round(base_size * scale))
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            try:
                return ImageFont.truetype(fallback_path, size)
            except Exception:
                return ImageFont.load_default()

    title_font = scaled_font(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        140,
    )
    subtitle_font = scaled_font(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        44,
    )
    footer_font = scaled_font(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
        34,
    )

    # 1. Logo (créé avec PIL, puis inséré comme image)
    logo_size = round(220 * scale)
    logo_img = create_logo_image(size=logo_size)
    logo_x, logo_y = round(250 * scale), round(280 * scale)
    title_img.paste(logo_img, (logo_x, logo_y), logo_img)

    # 2. Titre principal "Klepsydrix"
    title_text = APP_SETTINGS["title"]
    title_x, title_y = round(550 * scale), round(300 * scale)
    draw.text((title_x, title_y), title_text, fill=(24, 32, 43), font=title_font)

    # 3. Sous-titre (multi-ligne)
    subtitle_text = APP_SETTINGS["subtitle"]
    subtitle_lines = subtitle_text.split('\n')
    line_height = round(50 * scale)
    subtitle_y = round(550 * scale)
    for line in subtitle_lines:
        line_bbox = draw.textbbox((0, 0), line, font=subtitle_font)
        line_width = line_bbox[2] - line_bbox[0]
        line_x = (W - line_width) // 2
        draw.text((line_x, subtitle_y), line, fill=(80, 80, 80), font=subtitle_font)
        subtitle_y += line_height

    # 4. Barre accent (couleur de la marque)
    bar_width = round(1000 * scale)
    bar_x = (W - bar_width) // 2
    bar_y = round(780 * scale)
    bar_height = max(2, round(8 * scale))
    draw.rectangle(
        [(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)],
        fill=APP_SETTINGS["accent_color"]
    )

    # 5. Footer
    footer_text = APP_SETTINGS["footer_tagline"]
    footer_bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
    footer_width = footer_bbox[2] - footer_bbox[0]
    footer_x = (W - footer_width) // 2
    footer_y = round(850 * scale)
    draw.text((footer_x, footer_y), footer_text, fill=(120, 120, 120), font=footer_font)

    # Sauvegarder l'image
    title_card_path = AUDIO_DIR / "title_card.png"
    title_img.save(title_card_path)
    print(f"  ✅ Page de garde générée avec PIL ({W}x{H})")

    # Créer le clip vidéo à partir de l'image
    return mp.ImageClip(str(title_card_path)).with_duration(duration)


# --- MONTAGE ---
def assemble(video_path, durations, audio_paths, timestamps):
    print("🎬 Phase Montage Final...")
    if not os.path.exists(video_path):
        print("  ❌ Fichier vidéo source introuvable.")
        return

    full_video = mp.VideoFileClip(video_path)

    intro_audio_dur = durations.get("01_intro", 5.0)
    intro_total_dur = intro_audio_dur + 1.5
    intro_animation = create_title_card(intro_total_dur)

    # Pas de "saut temporel" pour cette démo : on concatène simplement la page de garde
    # et la capture complète.
    rest_of_video = full_video.subclipped(intro_total_dur, full_video.duration)
    video = mp.concatenate_videoclips([intro_animation, rest_of_video])

    # --- AUDIO ---
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

    out_name = f"DEMO_KLEPSYDRIX_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
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
        for svc in APP_SETTINGS["services"]:
            if not wait_for_service(svc):
                return

    durations, audio_paths = generate_audio()

    if assemble_only:
        if not meta_path.exists():
            print("  ❌ Aucun fichier 'last_meta.json' trouvé. Lancez une capture complète d'abord.")
            return

        print("⚡ Mode Montage Seul activé. Réutilisation de la dernière capture...")
        with open(meta_path, "r") as f:
            meta = json.load(f)
            t_marks = meta["timestamps"]
            v_path = meta.get("video_path")

        if not v_path or not os.path.exists(v_path):
            webms = list(VIDEO_DIR.glob("*.webm"))
            if not webms:
                print("  ❌ Aucune vidéo .webm trouvée dans temp_video/")
                return
            v_path = str(max(webms, key=os.path.getmtime))
            print(f"  🎬 Vidéo détectée : {v_path}")

        assemble(v_path, durations, audio_paths, t_marks)
    else:
        try:
            v_path, t_marks = await capture(durations)
            if v_path:
                with open(meta_path, "w") as f:
                    json.dump({
                        "video_path": v_path,
                        "timestamps": t_marks
                    }, f, indent=2)

                assemble(v_path, durations, audio_paths, t_marks)
        except Exception as e:
            print(f"❌ Échec global : {e}")
            import traceback
            traceback.print_exc()

    # Afficher le temps d'exécution
    elapsed_time = time.time() - script_start_time
    minutes, seconds = divmod(elapsed_time, 60)
    print("\n" + "="*60)
    print(f"✨ Script terminé en {int(minutes)}m {seconds:.1f}s ({elapsed_time:.1f}s total)")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
