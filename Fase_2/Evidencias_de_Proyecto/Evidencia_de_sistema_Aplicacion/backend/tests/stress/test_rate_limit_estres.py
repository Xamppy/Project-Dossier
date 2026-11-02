"""S5.8 · Limitador bajo concurrencia y volumen (pruebas de estrés)."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from dossier.security import rate_limit as rl


def test_concurrencia_doscientas_peticiones_simultaneas_respetan_el_limite_exacto():
    """Sin el candado, dos hilos podrían leer el mismo conteo y pasar los dos."""
    lim = rl.SlidingWindowLimiter(lambda: rl.Limit(25, 60))

    with ThreadPoolExecutor(max_workers=32) as pool:
        resultados = list(pool.map(lambda _: lim.hit("misma-ip"), range(200)))

    assert sum(1 for r in resultados if r is None) == 25


def test_volumen_cien_mil_claves_distintas_no_crecen_sin_limite():
    """Un atacante que rota IPs no debe agotar la memoria del proceso."""
    lim = rl.SlidingWindowLimiter(lambda: rl.Limit(5, 60), max_keys=10_000)

    inicio = time.perf_counter()
    for i in range(100_000):
        lim.hit(f"ip-{i}")

    assert lim.key_count() <= 10_000
    assert time.perf_counter() - inicio < 5.0


def test_degradacion_configuracion_rota_no_bloquea_la_api(monkeypatch):
    """Un valor mal escrito en el entorno usa el valor por omisión; nunca deja la API cerrada."""
    monkeypatch.setenv("AUTH_RATE_LIMIT", "veinte por minuto")
    lim = rl.SlidingWindowLimiter(lambda: rl.limit_from_env("AUTH_RATE_LIMIT", rl.Limit(20, 60)))

    assert all(lim.hit("ip") is None for _ in range(20))
    assert lim.hit("ip") is not None
