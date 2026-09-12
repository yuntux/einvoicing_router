from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def make_engine(database_url: str | None = None):
    url = database_url or settings.database_url
    is_sqlite = url.startswith("sqlite")
    if is_sqlite:
        # SQLite ouvre le fichier directement, sans jamais créer les répertoires
        # parents manquants (contrairement à un serveur de base de données) — les
        # créer nous-mêmes évite un OperationalError "unable to open database file"
        # au premier déploiement, avant toute migration/écriture.
        db_path = make_url(url).database
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # timeout=30 : le scheduler (polling/retry/purge, § 4.1/§ 4.7) et les requêtes
    # IHM ouvrent des connexions concurrentes au même fichier SQLite — sans ce délai
    # d'attente, la moindre collision d'écriture lève immédiatement "database is
    # locked" (timeout par défaut du driver sqlite3 : 5s, trop court en pratique,
    # notamment pendant la fenêtre de bascule d'un redémarrage du service).
    connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}
    engine = create_engine(url, connect_args=connect_args)
    if is_sqlite:
        # PRAGMA busy_timeout, en plus du paramètre timeout ci-dessus : appartient à
        # la connexion elle-même (toujours applicable, jamais de contention).
        # PRAGMA journal_mode=WAL : contrairement au mode rollback-journal par défaut,
        # une lecture n'attend plus jamais un écrivain en cours (seules deux écritures
        # concurrentes se sérialisent encore) — sans ça, la moindre requête IHM en
        # lecture (ex. l'allowlist IP vérifiée à chaque appel, cf. ip_allowlist.py)
        # peut échouer en "database is locked" pendant qu'une écriture est en cours
        # ailleurs (scheduler, autre requête), le busy_timeout ne faisant qu'attendre
        # avant d'échouer, jamais résoudre la contention. Le réglage est persistant
        # (stocké dans le fichier), mais s'applique explicitement à chaque connexion
        # du pool par simplicité et idempotence.
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


engine = make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
