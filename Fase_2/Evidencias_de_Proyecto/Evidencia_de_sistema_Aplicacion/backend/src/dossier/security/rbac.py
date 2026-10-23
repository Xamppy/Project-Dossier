"""RBAC de organización (Sección 9.3 del informe de producto)."""
from __future__ import annotations

from typing import Literal

OrgRole = Literal["admin", "user", "viewer", "api_user"]
MutatingOrgRole = Literal["admin", "user"]

ALLOWED_ORG_ROLES: frozenset[str] = frozenset({"admin", "user", "viewer", "api_user"})

# Orden jerárquico para comparaciones (api_user se trata como user hasta integrar API keys).
_ROLE_RANK: dict[str, int] = {
    "viewer": 0,
    "user": 1,
    "api_user": 1,
    "admin": 2,
}


def normalize_org_role(role: str | None) -> OrgRole:
    raw = (role or "user").strip().lower()
    if raw not in ALLOWED_ORG_ROLES:
        return "user"
    return raw  # type: ignore[return-value]


def role_at_least(role: str | None, minimum: MutatingOrgRole | Literal["admin"]) -> bool:
    """True si ``role`` tiene al menos el nivel de ``minimum``."""
    r = normalize_org_role(role)
    min_r = normalize_org_role(minimum)
    return _ROLE_RANK.get(r, 0) >= _ROLE_RANK.get(min_r, 0)


def can_mutate_dossiers(role: str | None) -> bool:
    """Admin y User pueden generar/editar/eliminar (según ownership). Viewer no."""
    return role_at_least(role, "user")


def can_manage_organization(role: str | None) -> bool:
    return normalize_org_role(role) == "admin"
