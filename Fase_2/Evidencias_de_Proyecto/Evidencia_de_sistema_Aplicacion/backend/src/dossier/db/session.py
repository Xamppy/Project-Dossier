"""Sesiones SQLAlchemy para FastAPI (Depends) o uso manual."""
from __future__ import annotations

import importlib.util
import sys
from collections.abc import Generator
from pathlib import Path

if importlib.util.find_spec("dossier") is None:
    _here = Path(__file__).resolve().parent
    for _root in [_here, *_here.parents]:
        if (_root / "dossier" / "__init__.py").is_file():
            sys.path.insert(0, str(_root))
            break

from sqlalchemy.orm import Session, sessionmaker

from dossier.db.connection import get_engine

_session_factory: sessionmaker[Session] | None = None


def _factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """
    Dependencia FastAPI:

        @app.get("/ejemplo")
        def ejemplo(db: Session = Depends(get_db)):
            ...
    """
    factory = _factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
