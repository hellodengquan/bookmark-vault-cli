import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

_engine = None
_SessionLocal = None
_current_db_path = None


def _default_db_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "bookmarks.db")


def _ensure_db_dir(db_path: str) -> None:
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)


def get_configured_db_path() -> str:
    global _current_db_path
    if _current_db_path is not None:
        return _current_db_path
    from app.config import load_config
    cfg = load_config()
    db_path = cfg.db_path
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(db_path)
    _current_db_path = db_path
    return _current_db_path


def set_db_path(db_path: str) -> None:
    global _current_db_path
    _current_db_path = db_path


def get_engine(db_path: str | None = None):
    global _engine, _current_db_path, _SessionLocal
    if db_path is None:
        db_path = get_configured_db_path()
    if _engine is not None and db_path == _current_db_path:
        return _engine

    if _engine is not None:
        _engine.dispose()

    _ensure_db_dir(db_path)
    url = f"sqlite:///{db_path}"
    _engine = create_engine(
        url,
        connect_args={"check_same_thread": False}
    )

    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    _current_db_path = db_path
    _SessionLocal = None
    return _engine


def get_session_factory(db_path: str | None = None):
    global _SessionLocal
    eng = get_engine(db_path)
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    return _SessionLocal


def init_database(db_path: str | None = None) -> None:
    import app.models  # noqa: F401 — ensure tables are registered in Base.metadata
    eng = get_engine(db_path)
    Base.metadata.create_all(bind=eng)


def get_db():
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def reset_engine() -> None:
    global _engine, _SessionLocal, _current_db_path
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    _current_db_path = None
