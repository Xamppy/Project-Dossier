"""SEC-2026-10-19-01 · Versiones mínimas de dependencias con vulnerabilidades conocidas.

Origen: auditorías del 2026-10-19 (docs/evidencias/fase2/calidad/05-pip-audit.txt y
06-npm-audit.txt) y la nueva corrida del 2026-10-22, que elevó `next` a severidad crítica.

Estas pruebas no reemplazan a pip-audit ni a npm audit: impiden que una versión
vulnerable vuelva a fijarse por error (por ejemplo, al resolver un conflicto).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REQUIREMENTS = PROJECT_ROOT / "backend" / "requirements.txt"
PACKAGE_JSON = PROJECT_ROOT / "frontend" / "package.json"

# Primera versión sin los avisos conocidos.
PYJWT_MINIMA = (2, 15, 0)  # PYSEC-2026-4141 y PYSEC-2026-4183
NEXT_MINIMA = (16, 4, 2)  # GHSA-cjq9-62q9-8jv4 (SSRF), envenenamiento de caché y otros


def _version(texto: str) -> tuple[int, ...]:
    """'2.15.0' -> (2, 15, 0). Falla si no es una versión exacta."""
    assert re.fullmatch(r"\d+(\.\d+)*", texto), f"versión no exacta: {texto!r}"
    return tuple(int(p) for p in texto.split("."))


def _pin_de_requirements(paquete: str) -> str:
    for linea in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        nombre, sep, version = linea.strip().partition("==")
        if sep and nombre.lower() == paquete.lower():
            return version.strip()
    raise AssertionError(f"{paquete} no está fijado con == en requirements.txt")


def _dependencias_frontend() -> dict[str, str]:
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    return {**data.get("dependencies", {}), **data.get("devDependencies", {})}


# --------------------------------------------------------------------------
# Backend
# --------------------------------------------------------------------------


def test_pyjwt_fijado_en_version_sin_avisos():
    assert _version(_pin_de_requirements("PyJWT")) >= PYJWT_MINIMA


def test_pyjwt_instalado_coincide_con_lo_fijado():
    """El entorno que corre la suite usa la versión corregida, no una anterior."""
    import jwt

    assert jwt.__version__ == _pin_de_requirements("PyJWT")


def test_version_no_exacta_es_rechazada():
    """Caso de error del verificador: un rango no sirve como pin."""
    for texto in (">=2.15.0", "2.15.*", "^16.4.2", ""):
        try:
            _version(texto)
        except AssertionError:
            continue
        raise AssertionError(f"se aceptó {texto!r} como versión exacta")


# --------------------------------------------------------------------------
# Frontend
# --------------------------------------------------------------------------


def test_next_fijado_en_version_exacta_sin_avisos():
    assert _version(_dependencias_frontend()["next"]) >= NEXT_MINIMA


def test_eslint_config_next_acompana_a_next():
    deps = _dependencias_frontend()
    assert deps["eslint-config-next"] == deps["next"]
