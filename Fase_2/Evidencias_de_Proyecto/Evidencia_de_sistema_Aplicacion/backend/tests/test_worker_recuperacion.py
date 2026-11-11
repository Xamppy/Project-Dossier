"""El worker busca trabajos colgados al arrancar y luego cada intervalo (unitarias)."""
from __future__ import annotations

import pytest

from dossier.services.dossier_generation_worker import recovery_due, recovery_interval_seconds


def test_al_arrancar_siempre_barre():
    assert recovery_due(None, 5.0, 60.0) is True


@pytest.mark.parametrize(
    ("ultimo", "ahora", "toca"), [(100.0, 159.9, False), (100.0, 160.0, True), (100.0, 500.0, True)]
)
def test_despues_barre_cada_intervalo(ultimo, ahora, toca):
    assert recovery_due(ultimo, ahora, 60.0) is toca


@pytest.mark.parametrize(("valor", "esperado"), [(None, 60.0), ("120", 120.0), ("1", 10.0), ("x", 60.0)])
def test_intervalo_configurable_con_minimo(monkeypatch, valor, esperado):
    if valor is None:
        monkeypatch.delenv("DOSSIER_JOB_RECOVERY_SECONDS", raising=False)
    else:
        monkeypatch.setenv("DOSSIER_JOB_RECOVERY_SECONDS", valor)
    assert recovery_interval_seconds() == esperado
