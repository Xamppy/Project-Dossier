"""Registro de fuentes de noticias: descubre los adaptadores de esta carpeta (UX-ADMIN-02).

Un archivo es una fuente si expone ``PROVEEDOR``. Los que empiezan con ``_`` se ignoran
(la plantilla). Un adaptador que no importa, no cumple el contrato o repite una clave se
anota en el log y se omite: una fuente mal escrita nunca impide que arranque la API.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
import re
from functools import lru_cache

from dossier.news.proveedores.base import ProveedorNoticias

logger = logging.getLogger(__name__)

CLAVE_VALIDA = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
VARIABLE_VALIDA = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_PAQUETE = "dossier.news.proveedores"
# Módulos del paquete que son infraestructura, no fuentes.
_NO_SON_FUENTES = frozenset({"base", "registro"})


def validar_proveedor(proveedor: object) -> str | None:
    """Motivo por el que no cumple el contrato, o ``None`` si es válido."""
    if not isinstance(proveedor, ProveedorNoticias):
        return "PROVEEDOR no es una instancia de ProveedorNoticias"
    clave = getattr(proveedor, "clave", None)
    if not isinstance(clave, str) or not CLAVE_VALIDA.match(clave):
        return f"clave inválida {clave!r}: usa minúsculas, números y _ (2 a 40, empieza con letra)"
    nombre = getattr(proveedor, "nombre", None)
    if not isinstance(nombre, str) or not nombre.strip() or len(nombre) > 80:
        return f"nombre inválido en {clave!r}: texto de 1 a 80 caracteres"
    variable = getattr(proveedor, "variable_clave", None)
    if variable is not None and (not isinstance(variable, str) or not VARIABLE_VALIDA.match(variable)):
        return f"variable de entorno inválida en {clave!r}: {variable!r} (MAYÚSCULAS_CON_GUION_BAJO)"
    return None


def descubrir_proveedores(paquete: str = _PAQUETE) -> dict[str, ProveedorNoticias]:
    """Fuentes válidas del paquete, ordenadas por nombre."""
    raiz = importlib.import_module(paquete)
    encontrados: dict[str, ProveedorNoticias] = {}
    for info in pkgutil.iter_modules(raiz.__path__):
        if info.name.startswith("_") or info.name in _NO_SON_FUENTES:
            continue
        try:
            modulo = importlib.import_module(f"{paquete}.{info.name}")
        except Exception:
            logger.exception("Fuente de noticias %r omitida: no se pudo importar", info.name)
            continue
        proveedor = getattr(modulo, "PROVEEDOR", None)
        if proveedor is None:
            continue
        problema = validar_proveedor(proveedor)
        if problema:
            logger.error("Fuente de noticias %r omitida: %s", info.name, problema)
            continue
        if proveedor.clave in encontrados:
            logger.error("Fuente de noticias %r omitida: la clave %r ya existe", info.name, proveedor.clave)
            continue
        encontrados[proveedor.clave] = proveedor
    return dict(sorted(encontrados.items(), key=lambda par: par[1].nombre.lower()))


@lru_cache(maxsize=1)
def _instalados() -> dict[str, ProveedorNoticias]:
    return descubrir_proveedores()


def proveedores_instalados() -> dict[str, ProveedorNoticias]:
    """Fuentes instaladas (se descubren una vez por proceso). Copia: no se altera el registro."""
    return dict(_instalados())
