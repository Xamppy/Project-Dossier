"""GDELT DOC 2.0: prensa mundial de los últimos 30 días, gratis y sin clave (ADR 0004)."""
from __future__ import annotations

from typing import Any

from dossier.news import client
from dossier.news.proveedores.base import ArticuloNoticia, ProveedorNoticias
from dossier.schemas.dossier_executive_payload import SourceType


def _articulo(crudo: dict[str, Any]) -> ArticuloNoticia | None:
    url = str(crudo.get("url") or "").strip()
    titulo = str(crudo.get("title") or "").strip()
    if not url or not titulo:
        return None
    publicado = crudo.get("seendate")
    # GDELT no trae bajada: el sistema arma un resumen genérico (que no cuenta para homónimos).
    return ArticuloNoticia(
        titulo=titulo,
        url=url,
        medio=str(crudo.get("domain") or "").strip() or None,
        publicado=str(publicado) if publicado else None,
        resumen=None,
    )


class Gdelt(ProveedorNoticias):
    clave = "gdelt_news"
    nombre = "GDELT DOC 2.0"
    descripcion = "Prensa mundial de los últimos 30 días. Gratis y sin clave."
    activo_por_defecto = True
    tipo_fuente = SourceType.gdelt_news

    def buscar(self, consulta: str, *, limite: int) -> list[ArticuloNoticia]:
        if not (consulta or "").strip():
            return []
        crudos = client.search_gdelt_articles(consulta, limite=limite)
        return [a for a in (_articulo(c) for c in crudos if isinstance(c, dict)) if a is not None]


PROVEEDOR = Gdelt()
