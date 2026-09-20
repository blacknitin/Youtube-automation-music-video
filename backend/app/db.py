"""SQLAlchemy engine/session (SQLite by default, PostgreSQL supported via DATABASE_URL)."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import SETTINGS

SETTINGS.data_dir.mkdir(parents=True, exist_ok=True)
SETTINGS.storage_dir.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if SETTINGS.db_url.startswith("sqlite") else {}
engine = create_engine(SETTINGS.db_url, connect_args=connect_args, pool_pre_ping=True)

if SETTINGS.db_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def init_db():
    from . import models  # noqa: F401  (register tables)
    Base.metadata.create_all(engine)

def db_session():
    return SessionLocal()

def get_db_dep():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
