"""Rutas del proyecto, .env y carpeta de salidas."""
from __future__ import annotations

import json
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PACKAGE_ROOT.parent
PROJECT_ROOT = SRC_ROOT.parent

DATA_DIR = PROJECT_ROOT / "data"
REPOSITORY_ROOT = PROJECT_ROOT.parent
DOCS_DIR = REPOSITORY_ROOT / "docs"


def load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")


def data_path(filename: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / filename


def write_json(data: dict, filename: str) -> Path:
    path = data_path(filename)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
