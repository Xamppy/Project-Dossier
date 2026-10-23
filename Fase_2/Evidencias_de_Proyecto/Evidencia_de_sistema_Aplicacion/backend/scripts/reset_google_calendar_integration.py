"""Borra la integración de Google Calendar guardada (token con scopes insuficientes).

Tras ejecutarlo, vuelve a conectar Google desde el dashboard para re-consentir
con el permiso de calendario (calendar.readonly).

Uso:
    python scripts/reset_google_calendar_integration.py
    python scripts/reset_google_calendar_integration.py --provider microsoft
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dossier.config import load_env

load_env()

from sqlalchemy import text

from dossier.db.connection import get_engine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        default="google",
        choices=["google", "microsoft"],
        help="Proveedor a reiniciar (por defecto: google).",
    )
    args = parser.parse_args()

    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM calendar_integrations WHERE provider = :p"),
            {"p": args.provider},
        )
        print(f"Filas borradas para provider={args.provider}: {result.rowcount}")
    print(
        f"\nListo. Ahora reconecta {args.provider} desde el dashboard "
        "(Resumen) para volver a autorizar con los permisos correctos."
    )


if __name__ == "__main__":
    main()
