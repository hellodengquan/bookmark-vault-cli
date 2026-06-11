import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

_engine = None
_SessionLocal = None


def _default_db_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "bookmarks.db")


def _ensure_db_dir(db_path: str) -> None:
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)


def get_engine(db_path: str | None = None):
    global _engine
    if _engine is not None and db_path is None:
        return _engine

    if db_path is None:
        db_path = _default_db_path()

    if _engine is None or db_path != _engine.url.database:
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

    return _engine


def get_session_factory(db_path: str | None = None):
    global _SessionLocal
    engine = get_engine(db_path)
    if _SessionLocal is None or engine != _engine.bind:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


def init_database(db_path: str | None = None) -> None:
    engine = get_engine(db_path)
    Base.metadata.create_all(bind=engine)


def get_db():
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
