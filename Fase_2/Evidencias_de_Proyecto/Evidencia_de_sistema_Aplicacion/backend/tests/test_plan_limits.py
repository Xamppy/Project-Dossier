"""UX-ADMIN-01 · Configuración del tope de dossiers a la vez (unitarias, sin base)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from dossier.schemas.admin import AdminPlanSettingPatch
from dossier.services.plan_limits import (
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_WINDOW_MINUTES,
    PLAN_ORDER,
    is_known_plan,
    window_minutes,
)


def test_valores_iniciales_aprobados():
    assert DEFAULT_MAX_CONCURRENT == {"free": 1, "pro": 3, "enterprise": 10}
    assert PLAN_ORDER == ("free", "pro", "enterprise")


@pytest.mark.parametrize(("valor", "esperado"), [(None, 30), ("45", 45), ("0", 30), ("-3", 30), ("x", 30)])
def test_ventana_configurable(monkeypatch, valor, esperado):
    if valor is None:
        monkeypatch.delenv("DOSSIER_CONCURRENCY_WINDOW_MINUTES", raising=False)
    else:
        monkeypatch.setenv("DOSSIER_CONCURRENCY_WINDOW_MINUTES", valor)
    assert window_minutes() == esperado
    assert DEFAULT_WINDOW_MINUTES == 30


@pytest.mark.parametrize(("plan", "conocido"), [("free", True), ("pro", True), ("enterprise", True), ("gold", False), ("FREE", False), ("", False)])
def test_planes_conocidos(plan, conocido):
    assert is_known_plan(plan) is conocido


@pytest.mark.parametrize("valor", [1, 3, 100])
def test_el_patch_acepta_enteros_del_rango(valor):
    assert AdminPlanSettingPatch(max_concurrent_dossiers=valor).max_concurrent_dossiers == valor


@pytest.mark.parametrize("valor", [0, 101, -1, 2.5, "3", True, None])
def test_el_patch_rechaza_lo_demas(valor):
    with pytest.raises(ValidationError):
        AdminPlanSettingPatch(max_concurrent_dossiers=valor)


def test_el_patch_no_acepta_campos_extra():
    with pytest.raises(ValidationError):
        AdminPlanSettingPatch(max_concurrent_dossiers=2, plan="enterprise")
