"""Motor SQLAlchemy (lazy); se crea solo cuando hace falta."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if importlib.util.find_spec("dossier") is None:
    _here = Path(__file__).resolve().parent
    for _root in [_here, *_here.parents]:
        if (_root / "dossier" / "__init__.py").is_file():
            sys.path.insert(0, str(_root))
            break

from dossier.db.settings import build_database_url

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_engine: Engine | None = None


def is_database_configured() -> bool:
    return build_database_url() is not None


def get_engine() -> Engine:
    """
    Motor singleton. Requiere DATABASE_URL o POSTGRES_* en .env.
    """
    global _engine
    if _engine is not None:
        return _engine

    url = build_database_url()
    if not url:
        raise RuntimeError(
            "PostgreSQL no está configurado. Copia .env.example a .env y define "
            "DATABASE_URL o POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD y POSTGRES_DB."
        )

    import logging

    from sqlalchemy import create_engine, text

    _engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=int(os.getenv("POSTGRES_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("POSTGRES_MAX_OVERFLOW", "10")),
    )
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        _engine.dispose()
        _engine = None
        raise

    logging.getLogger(__name__).info(
        "Conexión exitosa con PostgreSQL (motor SQLAlchemy inicializado)."
    )
    return _engine


def dispose_engine() -> None:
    """Cierra el pool (útil en tests o shutdown)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
