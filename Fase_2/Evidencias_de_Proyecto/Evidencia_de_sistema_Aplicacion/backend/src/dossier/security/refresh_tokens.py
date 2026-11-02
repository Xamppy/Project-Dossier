"""
Tokens de renovación de sesión (S3.9).

El token de acceso (JWT) dura 15 minutos. La sesión larga la sostiene un token de
renovación opaco que viaja en una cookie ``HttpOnly`` (ver ``api/refresh_cookie.py``):
JavaScript no puede leerlo, así que un XSS no puede llevárselo.

Reglas:
- En la base solo se guarda el hash SHA-256 del token, nunca el token.
- Cada renovación **rota** el token: el anterior queda revocado y se entrega uno nuevo
  con el mismo vencimiento (la sesión no se alarga renovando).
- Si llega un token ya rotado dentro de ``ROTATION_GRACE_SECONDS`` es una carrera normal
  entre pestañas (``refresh_rotated``). Fuera de esa ventana es reutilización de un token
  robado: se revocan **todas** las sesiones del usuario (``refresh_reused``).
- El token crudo empieza con ``p.`` (sesión recordada) o ``s.`` (solo esta sesión del
  navegador), para que la rotación conserve el tipo de cookie.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from dossier.db.models import RefreshToken

REFRESH_COOKIE_NAME = "dossier_refresh"
ROTATION_GRACE_SECONDS = 30
SESSION_ONLY_HOURS = 12
_DEFAULT_DAYS = 30
_MIN_DAYS, _MAX_DAYS = 1, 90

_FORMATO = re.compile(r"[ps]\.[A-Za-z0-9_-]{40,128}")


class RefreshTokenError(Exception):
    """Fallo de renovación con un código estable que el frontend puede interpretar."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RotationResult:
    user_id: UUID
    organization_id: UUID
    raw_token: str
    persistent: bool
    expires_at: datetime


def refresh_token_days() -> int:
    """Vigencia de una sesión recordada (``REFRESH_TOKEN_EXPIRE_DAYS``, 1 a 90; 30 por omisión)."""
    raw = (os.getenv("REFRESH_TOKEN_EXPIRE_DAYS") or "").strip()
    try:
        dias = int(raw)
    except ValueError:
        return _DEFAULT_DAYS
    return max(_MIN_DAYS, min(_MAX_DAYS, dias))


def expiry_for(*, persistent: bool, now: datetime) -> datetime:
    if persistent:
        return now + timedelta(days=refresh_token_days())
    return now + timedelta(hours=SESSION_ONLY_HOURS)


def new_raw_token(*, persistent: bool) -> str:
    return f"{'p' if persistent else 's'}.{secrets.token_urlsafe(48)}"


def is_persistent(raw: str) -> bool:
    return raw.startswith("p.")


def looks_valid(raw: str | None) -> bool:
    return bool(raw) and _FORMATO.fullmatch(raw or "") is not None


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _limitar(user_agent: str | None) -> str | None:
    return user_agent[:500] if user_agent else None


def issue(
    db: Session,
    *,
    user_id: UUID,
    organization_id: UUID,
    persistent: bool,
    ip: str | None = None,
    user_agent: str | None = None,
    now: datetime | None = None,
    expires_at: datetime | None = None,
) -> str:
    """Crea un token de renovación y devuelve el token crudo. No hace commit."""
    now = now or datetime.now(UTC)
    raw = new_raw_token(persistent=persistent)
    db.add(
        RefreshToken(
            user_id=user_id,
            organization_id=organization_id,
            token_hash=hash_refresh_token(raw),
            expires_at=expires_at or expiry_for(persistent=persistent, now=now),
            ip_address=ip,
            user_agent=_limitar(user_agent),
        )
    )
    db.flush()
    return raw


def revoke_all_for_user(db: Session, user_id: UUID, *, now: datetime | None = None) -> int:
    """Revoca todas las sesiones activas del usuario. Devuelve cuántas revocó. No hace commit."""
    now = now or datetime.now(UTC)
    resultado = db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked.is_(False))
        .values(is_revoked=True, revoked_at=now)
    )
    return int(getattr(resultado, "rowcount", 0) or 0)


def _bloquear(db: Session, raw: str) -> RefreshToken | None:
    # FOR UPDATE: dos renovaciones simultáneas del mismo token no pueden rotarlo dos veces.
    return db.execute(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw))
        .with_for_update()
    ).scalar_one_or_none()


def rotate(
    db: Session,
    raw: str | None,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
    now: datetime | None = None,
    still_allowed: Callable[[RefreshToken], bool] | None = None,
) -> RotationResult:
    """Valida el token, lo revoca y emite su reemplazo. **Hace commit** en todos los casos.

    ``still_allowed`` permite a la ruta rechazar la renovación (usuario desactivado o sin
    membresía): el token se revoca y se lanza ``refresh_inactive``.
    """
    if not raw:
        raise RefreshTokenError("refresh_missing")
    if not looks_valid(raw):
        raise RefreshTokenError("refresh_invalid")
    now = now or datetime.now(UTC)

    fila = _bloquear(db, raw)
    if fila is None:
        db.rollback()
        raise RefreshTokenError("refresh_invalid")

    if fila.is_revoked:
        if fila.revoked_at is not None and now - fila.revoked_at <= timedelta(seconds=ROTATION_GRACE_SECONDS):
            db.rollback()
            raise RefreshTokenError("refresh_rotated")
        revoke_all_for_user(db, fila.user_id, now=now)
        db.commit()
        raise RefreshTokenError("refresh_reused")

    fila.is_revoked = True
    fila.revoked_at = now
    if fila.expires_at <= now:
        db.commit()
        raise RefreshTokenError("refresh_expired")
    if still_allowed is not None and not still_allowed(fila):
        db.commit()
        raise RefreshTokenError("refresh_inactive")

    persistente = is_persistent(raw)
    nuevo = issue(
        db,
        user_id=fila.user_id,
        organization_id=fila.organization_id,
        persistent=persistente,
        ip=ip,
        user_agent=user_agent,
        now=now,
        expires_at=fila.expires_at,
    )
    db.commit()
    return RotationResult(
        user_id=fila.user_id,
        organization_id=fila.organization_id,
        raw_token=nuevo,
        persistent=persistente,
        expires_at=fila.expires_at,
    )


def rebind(
    db: Session,
    raw: str | None,
    organization_id: UUID,
    *,
    now: datetime | None = None,
) -> tuple[str, datetime] | None:
    """Mueve la sesión a otra organización (cambio de organización activa).

    Rota el token conservando vencimiento y tipo. Devuelve ``(token_nuevo, vence)`` o
    ``None`` si no había un token válido. No hace commit.
    """
    if not looks_valid(raw):
        return None
    assert raw is not None
    now = now or datetime.now(UTC)
    fila = _bloquear(db, raw)
    if fila is None or fila.is_revoked or fila.expires_at <= now:
        return None
    fila.is_revoked = True
    fila.revoked_at = now
    nuevo = issue(
        db,
        user_id=fila.user_id,
        organization_id=organization_id,
        persistent=is_persistent(raw),
        ip=str(fila.ip_address) if fila.ip_address else None,
        user_agent=fila.user_agent,
        now=now,
        expires_at=fila.expires_at,
    )
    return nuevo, fila.expires_at


def revoke(db: Session, raw: str | None, *, now: datetime | None = None) -> bool:
    """Revoca un token (cierre de sesión). Devuelve si había uno activo. No hace commit."""
    if not looks_valid(raw):
        return False
    assert raw is not None
    fila = _bloquear(db, raw)
    if fila is None or fila.is_revoked:
        return False
    fila.is_revoked = True
    fila.revoked_at = now or datetime.now(UTC)
    return True
