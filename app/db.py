"""Database engine + session helpers."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.config import ROOT_DIR, get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.database_url
        # Ensure sqlite parent dir exists for relative paths
        if db_url.startswith("sqlite:///"):
            rel = db_url.removeprefix("sqlite:///")
            path = Path(rel)
            if not path.is_absolute():
                path = ROOT_DIR / path
            path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{path}"
        _engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
        )
    return _engine


def init_db() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
