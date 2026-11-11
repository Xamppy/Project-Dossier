"""NewsAPI.org: buscador de noticias con clave (plan Developer gratis) (ADR 0004)."""
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
    fuente = crudo.get("source")
    medio = str(fuente.get("name") or "").strip() if isinstance(fuente, dict) else ""
    publicado = crudo.get("publishedAt")
    return ArticuloNoticia(
        titulo=titulo,
        url=url,
        medio=medio or None,
        publicado=str(publicado) if publicado else None,
        resumen=str(crudo.get("description") or "").strip() or None,
    )


class NewsApi(ProveedorNoticias):
    clave = "news_api"
    nombre = "NewsAPI"
    descripcion = "Buscador de noticias en inglés y otros idiomas. Requiere clave (plan gratis disponible)."
    variable_clave = "NEWS_API_KEY"
    activo_por_defecto = True
    tipo_fuente = SourceType.news_api

    def buscar(self, consulta: str, *, limite: int) -> list[ArticuloNoticia]:
        if not (consulta or "").strip():
            return []
        crudos = client.search_newsapi_articles(consulta, limite=limite)
        return [a for a in (_articulo(c) for c in crudos if isinstance(c, dict)) if a is not None]


PROVEEDOR = NewsApi()
