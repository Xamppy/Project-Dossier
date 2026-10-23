"""Aplica migraciones pendientes de calendario (event_snapshot, check de advance_minutes).

Uso:
    python scripts/apply_calendar_migrations.py

Idempotente: se puede ejecutar varias veces sin romper nada.
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
    "ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS event_snapshot JSONB;",
    "ALTER TABLE calendar_integrations DROP CONSTRAINT IF EXISTS calendar_integrations_advance_minutes_check;",
    "ALTER TABLE calendar_integrations ADD CONSTRAINT calendar_integrations_advance_minutes_check "
    "CHECK (advance_minutes IN (15, 20, 30, 60, 1440));",
]


def main() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        for sql in _STATEMENTS:
            print(f"-> {sql}")
            conn.execute(text(sql))
    print("\nMigraciones de calendario aplicadas correctamente.")


if __name__ == "__main__":
    main()
