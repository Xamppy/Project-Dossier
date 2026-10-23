"""Conexión PostgreSQL vía variables de entorno (cada máquina tiene su .env)."""

from dossier.db.connection import (
    dispose_engine,
    get_engine,
    is_database_configured,
)
from dossier.db.session import get_db
from dossier.db.settings import build_database_url

__all__ = [
    "build_database_url",
    "dispose_engine",
    "get_db",
    "get_engine",
    "is_database_configured",
]
