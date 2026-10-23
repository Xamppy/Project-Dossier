"""
Punto de entrada del servidor (directorio backend/).
Toda la lógica vive en `src/dossier/`; aquí solo se ajusta el path y se arranca uvicorn.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "src"))

from dossier.config import load_env

load_env()

from dossier.api.app import app

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    print()
    print("  Sistema Dossier — API FastAPI")
    print("  -------------------------------")
    print("  Local:    http://127.0.0.1:8000")
    print("  Docs:     http://127.0.0.1:8000/docs")
    print("  Salud:    http://127.0.0.1:8000/health")
    print("  Base BD:  http://127.0.0.1:8000/db/health")
    print()
    print("  También:  uvicorn dossier.api.app:app --reload  (desde backend/ con PYTHONPATH=src)")
    print()
    print("  Ctrl+C para detener el servidor.")
    print()
    uvicorn.run(app, host="127.0.0.1", port=8000)
