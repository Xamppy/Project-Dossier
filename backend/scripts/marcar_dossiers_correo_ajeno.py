"""Marca dossiers de calendario guardados con el correo de otro asistente (BUG-2026-10-19-07).

Por defecto solo simula e imprime el informe JSON. No borra nada y es idempotente.

Uso (desde backend/, con DATABASE_URL en .env):
    python scripts/marcar_dossiers_correo_ajeno.py            # simulación
    python scripts/marcar_dossiers_correo_ajeno.py --dry-run  # simulación, explícito
    python scripts/marcar_dossiers_correo_ajeno.py --aplicar  # escribe
"""
from __future__ import annotations

import _bootstrap  # noqa: F401  (añade src/ al path)

from dossier.config import load_env

load_env()

from dossier.services.dossiers_correo_ajeno import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
