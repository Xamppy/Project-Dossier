"""PLANTILLA para agregar una fuente de noticias. Este archivo NO se carga (empieza con «_»).

Pasos (guía completa en ``docs/tecnica/agregar-fuente-noticias.md``):

1. Copia este archivo con el nombre de la fuente, sin «_» al inicio: ``mi_fuente.py``.
2. Cambia ``clave``, ``nombre``, ``descripcion`` y ``variable_clave``.
3. Ajusta ``buscar``: la URL, los parámetros y cómo leer cada nota de la respuesta.
4. Pon la clave en el entorno del servidor (``.env`` o el gestor de secretos), por ejemplo
   ``MI_FUENTE_API_KEY=...``. Nunca en el código ni en la base de datos.
5. Corre las pruebas de contrato: ``pytest tests/test_news_proveedores.py``. Recorren todas las
   fuentes instaladas, incluida la nueva.
6. Reinicia la API. La fuente aparece **apagada** en Administración → Fuentes de noticias;
   el administrador la activa y define planes, profundidad, créditos extra y límite diario.

El sistema se encarga del resto: consulta en paralelo con las demás fuentes, tiempo máximo,
deduplicación, filtro de homónimos, cobro, límite diario y la tarjeta «Prensa».
"""
from __future__ import annotations

from typing import Any

import requests

from dossier.news.proveedores import ArticuloNoticia, ProveedorNoticias, ProveedorNoticiasError

# Dirección de búsqueda de la API (ejemplo ficticio).
URL_BUSQUEDA = "https://api.ejemplo-noticias.example/v1/search"
TIEMPO_MAXIMO_SEG = 20


def _articulo(crudo: dict[str, Any]) -> ArticuloNoticia | None:
    """Convierte una nota de la respuesta. Sin título o sin URL no sirve: ``None``."""
    titulo = str(crudo.get("headline") or "").strip()
    url = str(crudo.get("link") or "").strip()
    if not titulo or not url:
        return None
    return ArticuloNoticia(
        titulo=titulo,
        url=url,
        medio=str(crudo.get("publication") or "").strip() or None,
        publicado=str(crudo.get("published_at") or "").strip() or None,  # ISO 8601
        resumen=str(crudo.get("snippet") or "").strip() or None,
    )


class MiFuente(ProveedorNoticias):
    # Identificador estable: minúsculas, números y «_». No lo cambies una vez en uso.
    clave = "mi_fuente"
    # Lo que ve el administrador y lo que se cita como fuente en el dossier.
    nombre = "Mi Fuente de Noticias"
    descripcion = "Qué cubre, idiomas y costo, para que el administrador decida."
    # Variable de entorno con la clave de la API (None si la API no usa clave).
    variable_clave = "MI_FUENTE_API_KEY"
    # Las fuentes nuevas empiezan apagadas: las activa el administrador.
    activo_por_defecto = False

    def buscar(self, consulta: str, *, limite: int) -> list[ArticuloNoticia]:
        if not (consulta or "").strip():
            return []
        try:
            resp = requests.get(
                URL_BUSQUEDA,
                params={"q": consulta, "limit": str(limite)},
                # La clave va en una cabecera, nunca en la URL (las URL quedan en los logs).
                headers={"Authorization": f"Bearer {self.clave_api()}"},
                timeout=TIEMPO_MAXIMO_SEG,
            )
            resp.raise_for_status()
            datos = resp.json()
        except ProveedorNoticiasError:
            raise
        except Exception as exc:
            # Mensaje sin la clave ni la respuesta completa: va al log y al registro de fuentes.
            raise ProveedorNoticiasError(f"Error al consultar {self.nombre}: {type(exc).__name__}") from exc
        notas = datos.get("results") if isinstance(datos, dict) else None
        if not isinstance(notas, list):
            raise ProveedorNoticiasError(f"Respuesta inesperada de {self.nombre}")
        return [a for a in (_articulo(n) for n in notas if isinstance(n, dict)) if a is not None][:limite]


# El registro busca esta variable: sin ella, el archivo no es una fuente.
PROVEEDOR = MiFuente()
