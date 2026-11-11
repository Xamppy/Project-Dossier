"""Fuentes de noticias enchufables (UX-ADMIN-02).

Cada archivo de esta carpeta que expone ``PROVEEDOR`` es una fuente; el registro
(``registro.py``) los descubre solo. Los archivos que empiezan con ``_`` se ignoran: ahí está
la plantilla para copiar. Guía: ``docs/tecnica/agregar-fuente-noticias.md``.
"""
from dossier.news.client import ProveedorNoticiasError
from dossier.news.proveedores.base import ArticuloNoticia, ProveedorNoticias

__all__ = ["ArticuloNoticia", "ProveedorNoticias", "ProveedorNoticiasError"]
