"""S6.5, unitarias: plazo de retención, intervalo del worker y caché de Redis.

Especificación: ``specs/proposals/S6.5-retencion-24h.md`` (CA1, CA8, CA9, CA10).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dossier.cache import corporate_dossier_redis as cache
from dossier.services import dossier_retention_worker as worker
from dossier.services.dossier_retention import dossier_retention_hours, retention_cutoff

# --------------------------------------------------------------------------
# CA1 · plazo configurable, 24 h por omisión
# --------------------------------------------------------------------------


def test_sin_variable_la_retencion_es_de_24_horas(monkeypatch):
    monkeypatch.delenv("DOSSIER_RETENTION_HOURS", raising=False)
    assert dossier_retention_hours() == 24


def test_la_variable_cambia_el_plazo(monkeypatch):
    monkeypatch.setenv("DOSSIER_RETENTION_HOURS", "6")
    assert dossier_retention_hours() == 6


@pytest.mark.parametrize("valor", ["0", "-3", "dos", "", "  "])
def test_un_valor_invalido_vuelve_a_24_horas(monkeypatch, valor):
    monkeypatch.setenv("DOSSIER_RETENTION_HOURS", valor)
    assert dossier_retention_hours() == 24


def test_el_corte_es_ahora_menos_el_plazo(monkeypatch):
    monkeypatch.delenv("DOSSIER_RETENTION_HOURS", raising=False)
    ahora = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    assert retention_cutoff(ahora) == ahora - timedelta(hours=24)


# --------------------------------------------------------------------------
# CA10 · el worker revisa cada 10 minutos, nunca menos de 1
# --------------------------------------------------------------------------


def test_el_worker_revisa_cada_10_minutos_por_omision(monkeypatch):
    monkeypatch.delenv("DOSSIER_RETENTION_POLL_SECONDS", raising=False)
    assert worker.poll_interval_seconds() == 600


def test_el_intervalo_nunca_baja_de_60_segundos(monkeypatch):
    monkeypatch.setenv("DOSSIER_RETENTION_POLL_SECONDS", "5")
    assert worker.poll_interval_seconds() == 60


# --------------------------------------------------------------------------
# CA9 · la caché de Redis nunca dura más que la retención
# --------------------------------------------------------------------------


def test_el_ttl_de_redis_no_supera_la_retencion(monkeypatch):
    monkeypatch.setenv("DOSSIER_REDIS_TTL_SECONDS", str(30 * 24 * 3600))
    monkeypatch.setenv("DOSSIER_RETENTION_HOURS", "24")
    assert cache.redis_ttl_seconds() == 24 * 3600


def test_el_ttl_sigue_la_retencion_si_se_acorta(monkeypatch):
    monkeypatch.delenv("DOSSIER_REDIS_TTL_SECONDS", raising=False)
    monkeypatch.setenv("DOSSIER_RETENTION_HOURS", "2")
    assert cache.redis_ttl_seconds() == 2 * 3600


def test_un_ttl_menor_que_la_retencion_se_respeta(monkeypatch):
    monkeypatch.setenv("DOSSIER_REDIS_TTL_SECONDS", "3600")
    monkeypatch.setenv("DOSSIER_RETENTION_HOURS", "24")
    assert cache.redis_ttl_seconds() == 3600


# --------------------------------------------------------------------------
# CA8 · comprobar que la clave de Redis ya no existe
# --------------------------------------------------------------------------


class _RedisFalso:
    def __init__(self, claves):
        self.claves = set(claves)

    def exists(self, *keys):
        return sum(1 for k in keys if k in self.claves)

    def delete(self, *keys):
        antes = len(self.claves)
        self.claves -= set(keys)
        return antes - len(self.claves)


def test_existe_la_clave_mientras_no_se_borra(monkeypatch):
    falso = _RedisFalso({"dossier:corp:abc"})
    monkeypatch.setattr(cache, "_client", lambda: falso)
    assert cache.dossier_redis_key_exists("dossier:corp:abc") is True
    cache.delete_dossier_redis_cache("dossier:corp:abc")
    assert cache.dossier_redis_key_exists("dossier:corp:abc") is False


def test_sin_redis_la_clave_no_existe(monkeypatch):
    monkeypatch.setattr(cache, "_client", lambda: None)
    assert cache.dossier_redis_key_exists("dossier:corp:abc") is False


def test_clave_vacia_no_existe(monkeypatch):
    monkeypatch.setattr(cache, "_client", lambda: _RedisFalso({""}))
    assert cache.dossier_redis_key_exists("  ") is False
