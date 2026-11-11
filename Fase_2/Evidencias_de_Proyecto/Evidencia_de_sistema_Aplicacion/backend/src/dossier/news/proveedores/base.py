"""Contrato de una fuente de noticias (UX-ADMIN-02).

Una fuente es una subclase de ``ProveedorNoticias`` con cuatro datos y un método:

- ``clave``: identificador estable en minúsculas (``^[a-z][a-z0-9_]{1,39}$``). Es la llave de
  sus ajustes en ``news_source_settings``: no se cambia una vez en uso.
- ``nombre``: lo que ve el administrador y lo que se cita como fuente en el dossier.
- ``variable_clave``: variable de entorno con la clave de la API (``None`` si no usa clave).
  La clave vive solo en el servidor; el panel muestra si está configurada, nunca su valor.
- ``activo_por_defecto``: si se usa sin que el admin la active. Las fuentes nuevas, ``False``.
- ``buscar(consulta, limite)``: devuelve ``ArticuloNoticia``. Ante cualquier fallo lanza
  ``ProveedorNoticiasError`` con un mensaje sin la clave ni la URL completa.

La deduplicación, el filtro de homónimos, el cobro y los límites los hace el sistema.
Guía completa: ``docs/tecnica/agregar-fuente-noticias.md``.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from dossier.news.client import ProveedorNoticiasError
from dossier.schemas.dossier_executive_payload import SourceType


@dataclass(frozen=True)
class ArticuloNoticia:
    """Una nota de prensa tal como la entrega la fuente, ya en el formato del sistema."""

    titulo: str
    url: str
    medio: str | None = None
    # ISO 8601 (``2026-11-01T10:00:00Z``) o el formato compacto de GDELT (``20261101T100000Z``).
    publicado: str | None = None
    # Bajada o extracto real de la fuente. ``None`` si no trae: el sistema arma uno genérico.
    resumen: str | None = None


class ProveedorNoticias(ABC):
    """Una fuente de noticias que el sistema puede consultar."""

    clave: ClassVar[str]
    nombre: ClassVar[str]
    descripcion: ClassVar[str] = ""
    variable_clave: ClassVar[str | None] = None
    activo_por_defecto: ClassVar[bool] = False
    # Tipo de cita en el dossier. Las fuentes agregadas por el cliente usan ``news_provider``.
    tipo_fuente: ClassVar[SourceType] = SourceType.news_provider

    def configurado(self) -> bool:
        """Lista para consultar: no necesita clave, o su variable de entorno tiene valor.

        No carga el ``.env``: lo hace la API al arrancar. Cargarlo aquí metería en el entorno
        variables ajenas (p. ej. ``DOSSIER_CHARGE_CREDITS``) en cualquier momento.
        """
        if not self.variable_clave:
            return True
        return bool((os.getenv(self.variable_clave) or "").strip())

    def clave_api(self) -> str:
        """El valor de ``variable_clave``; error del proveedor si falta."""
        valor = (os.getenv(self.variable_clave or "") or "").strip()
        if not valor:
            raise ProveedorNoticiasError(f"Falta {self.variable_clave} para consultar {self.nombre}")
        return valor

    @abstractmethod
    def buscar(self, consulta: str, *, limite: int) -> list[ArticuloNoticia]:
        """Notas que coinciden con ``consulta`` (máximo ``limite``). Consulta vacía: ``[]``."""
