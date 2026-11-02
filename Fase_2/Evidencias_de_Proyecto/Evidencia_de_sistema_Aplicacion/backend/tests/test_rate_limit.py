"""S5.8 · Limitador de tasa: ventana deslizante en memoria (pruebas unitarias).

Las rutas que lo usan se prueban en ``tests/integration/test_rate_limit_rutas.py``.
"""
from __future__ import annotations

import pytest

from dossier.security import rate_limit as rl


class Reloj:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _limitador(raw: str = "3/60", reloj: Reloj | None = None) -> rl.SlidingWindowLimiter:
    return rl.SlidingWindowLimiter(lambda: rl.parse_limit(raw, rl.Limit(1, 1)), clock=reloj or Reloj())


# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [("5/60", rl.Limit(5, 60)), (" 10 / 300 ", rl.Limit(10, 300)), ("1/1", rl.Limit(1, 1))],
)
def test_parse_lee_peticiones_por_segundos(crudo, esperado):
    assert rl.parse_limit(crudo, rl.Limit(9, 9)) == esperado


@pytest.mark.parametrize("crudo", ["off", "OFF", "0", "0/60"])
def test_parse_permite_desactivar(crudo):
    assert rl.parse_limit(crudo, rl.Limit(9, 9)) is None


@pytest.mark.parametrize("crudo", [None, "", "abc", "5", "5/", "/60", "-1/60", "5/0", "5/-3"])
def test_parse_invalido_usa_el_valor_por_omision(crudo):
    assert rl.parse_limit(crudo, rl.Limit(9, 9)) == rl.Limit(9, 9)


# --------------------------------------------------------------------------
# Ventana deslizante
# --------------------------------------------------------------------------


def test_permite_hasta_el_limite_y_luego_rechaza():
    lim = _limitador("3/60")
    assert [lim.hit("ip-1") for _ in range(3)] == [None, None, None]
    assert lim.hit("ip-1") == 60


def test_cada_clave_tiene_su_propio_contador():
    lim = _limitador("1/60")
    assert lim.hit("ip-1") is None
    assert lim.hit("ip-2") is None
    assert lim.hit("ip-1") is not None


def test_retry_after_cuenta_desde_la_peticion_mas_antigua():
    reloj = Reloj()
    lim = _limitador("2/60", reloj)
    lim.hit("k")
    reloj.t += 20
    lim.hit("k")
    reloj.t += 10

    assert lim.hit("k") == 30  # la primera sale de la ventana en 60 - 30 = 30 s


def test_pasada_la_ventana_vuelve_a_aceptar():
    reloj = Reloj()
    lim = _limitador("2/60", reloj)
    lim.hit("k")
    lim.hit("k")
    assert lim.hit("k") is not None

    reloj.t += 60.001

    assert lim.hit("k") is None


def test_un_rechazo_no_cuenta_como_peticion():
    """Si contara, quien insiste nunca saldría del bloqueo."""
    reloj = Reloj()
    lim = _limitador("1/60", reloj)
    lim.hit("k")
    for _ in range(50):
        lim.hit("k")
    reloj.t += 60.001
    assert lim.hit("k") is None


def test_check_consulta_sin_registrar():
    lim = _limitador("1/60")
    assert lim.check("k") is None
    assert lim.check("k") is None
    lim.hit("k")
    assert lim.check("k") == 60


def test_clear_libera_la_clave():
    lim = _limitador("1/60")
    lim.hit("k")
    lim.clear("k")
    assert lim.hit("k") is None


def test_desactivado_nunca_rechaza():
    lim = _limitador("off")
    assert all(lim.hit("k") is None for _ in range(1000))


def test_retry_after_minimo_un_segundo():
    reloj = Reloj()
    lim = _limitador("1/1", reloj)
    lim.hit("k")
    reloj.t += 0.9999
    assert lim.hit("k") == 1


def test_lee_la_configuracion_en_cada_llamada(monkeypatch):
    """Cambiar la variable de entorno aplica sin reiniciar el proceso (útil en pruebas y operación)."""
    lim = rl.SlidingWindowLimiter(lambda: rl.parse_limit(None, rl.Limit(1, 60)), clock=Reloj())
    monkeypatch.setenv("X_RL", "2/60")
    lim2 = rl.SlidingWindowLimiter(lambda: rl.limit_from_env("X_RL", rl.Limit(1, 60)), clock=Reloj())
    assert lim.hit("k") is None and lim.hit("k") is not None
    assert lim2.hit("k") is None and lim2.hit("k") is None and lim2.hit("k") is not None


# --------------------------------------------------------------------------
# Claves
# --------------------------------------------------------------------------


def test_la_clave_de_correo_no_distingue_mayusculas_ni_espacios():
    assert rl.email_key(" Ana@Example.COM ") == rl.email_key("ana@example.com")


def test_la_clave_de_correo_no_guarda_el_correo_en_claro():
    assert "ana@example.com" not in rl.email_key("ana@example.com")
