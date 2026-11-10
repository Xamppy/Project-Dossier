"""Enlaces de un solo uso para leer un dossier desde el correo (S6.2).

Decisión de FD (2026-11-10): el enlace abre solo ese dossier, en solo lectura y sin iniciar
sesión; se gasta al canjearlo y vence en 24 horas.

- El token (256 bits) viaja solo en el correo. En la base se guarda su SHA-256.
- Va en el fragmento de la URL (``/acceso#t=…``): el fragmento no llega a ningún servidor, así
  que no queda en logs.
- El canje es un único ``UPDATE … RETURNING``: dos canjes a la vez nunca ganan los dos.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from dossier.db.models import Dossier, DossierAccessLink

logger = logging.getLogger(__name__)

VIGENCIA_HORAS_POR_OMISION = 24


def vigencia_horas() -> int:
    raw = os.getenv("DOSSIER_ACCESS_LINK_HOURS", "").strip()
    try:
        horas = int(raw)
    except ValueError:
        return VIGENCIA_HORAS_POR_OMISION
    return horas if horas > 0 else VIGENCIA_HORAS_POR_OMISION


def nuevo_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _frontend_base_url() -> str:
    return (os.getenv("DOSSIER_FRONTEND_URL") or os.getenv("FRONTEND_URL") or "http://localhost:3000").rstrip("/")


def url_de_acceso(token: str) -> str:
    return f"{_frontend_base_url()}/acceso#t={token}"


def crear_enlace(db: Session, dossier: Dossier, *, user_id: UUID, now: datetime | None = None) -> str:
    """Crea un enlace para ``dossier`` y devuelve el token. No hace commit."""
    token = nuevo_token()
    db.add(
        DossierAccessLink(
            token_hash=hash_token(token),
            dossier_id=dossier.id,
            user_id=user_id,
            organization_id=dossier.organization_id,
            expires_at=(now or datetime.now(UTC)) + timedelta(hours=vigencia_horas()),
        )
    )
    db.flush()
    return token


def url_de_acceso_o_nada(db: Session, dossier: Dossier, *, user_id: UUID) -> str | None:
    """Crea el enlace y devuelve su URL; si no se puede, ``None`` y el correo usa el dashboard.

    Va en un savepoint: un fallo aquí no rompe la transacción de quien envía el correo.
    """
    try:
        with db.begin_nested():
            return url_de_acceso(crear_enlace(db, dossier, user_id=user_id))
    except Exception:
        logger.warning("No se pudo crear el enlace de acceso del dossier %s", dossier.id, exc_info=True)
        return None


def canjear_enlace(db: Session, token: str, *, now: datetime | None = None) -> Dossier | None:
    """Gasta el enlace y devuelve su dossier, o ``None`` si no sirve. Hace commit.

    No distingue por qué no sirve (inexistente, usado, vencido, dossier borrado o incompleto).
    """
    if not token or len(token) > 200:
        return None
    ahora = now or datetime.now(UTC)
    dossier_id = db.execute(
        update(DossierAccessLink)
        .where(
            DossierAccessLink.token_hash == hash_token(token),
            DossierAccessLink.used_at.is_(None),
            DossierAccessLink.expires_at > ahora,
        )
        .values(used_at=ahora)
        .returning(DossierAccessLink.dossier_id)
    ).scalar_one_or_none()
    db.commit()
    if dossier_id is None:
        return None
    dossier = db.get(Dossier, dossier_id)
    if dossier is None or dossier.status != "complete":
        return None
    return dossier
