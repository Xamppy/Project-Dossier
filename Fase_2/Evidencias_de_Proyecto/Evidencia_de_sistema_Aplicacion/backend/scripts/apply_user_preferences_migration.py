"""Añade ``users.dossier_output_language`` para sincronizar idioma de dossiers con la UI.

Uso:
    python scripts/apply_user_preferences_migration.py

Idempotente.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dossier.config import load_env

load_env()

from sqlalchemy import text

from dossier.db.connection import get_engine

_STATEMENTS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS dossier_output_language VARCHAR(10) NOT NULL DEFAULT 'match';",
]


def main() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        for sql in _STATEMENTS:
            print(f"-> {sql}")
            conn.execute(text(sql))
    print("\nMigración de preferencias de usuario aplicada correctamente.")


if __name__ == "__main__":
    main()
