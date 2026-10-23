"""Tipo de espacio de trabajo del tenant (`organizations.settings.workspace_kind`)."""
from __future__ import annotations

from typing import Literal

from dossier.db.models import Organization

WORKSPACE_KIND_KEY = "workspace_kind"
# Valor de `organizations.name` para cuentas personales (marcador interno; la UI usa `workspace_kind`).
ORG_NAME_PERSONAL_PLACEHOLDER = "Personal"


def read_workspace_kind(org: Organization) -> Literal["personal", "work"]:
    """Por defecto `work` si no hay clave (organizaciones creadas antes de este campo)."""
    raw = org.settings if isinstance(org.settings, dict) else {}
    k = raw.get(WORKSPACE_KIND_KEY)
    if k == "personal":
        return "personal"
    return "work"
