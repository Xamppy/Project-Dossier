"""S5.2 · Generador SSE de la lista de dossiers para las notificaciones (unitarias).

El generador no conoce FastAPI ni la base: recibe dos lectores asíncronos (huella y
lista) y un reloj y un ``sleep`` falsos, así que se prueba sin servidor ni Postgres.
La ruta real está en tests/integration/test_dossier_notifications_route.py.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from dossier.services.dossier_notifications_stream import (
    DEFAULT_CHECK_SECONDS,
    DEFAULT_MAX_SECONDS,
    check_seconds,
    max_seconds,
    stream_dossier_list,
)


class _Reloj:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    async def dormir(self, segundos: float) -> None:
        self.t += segundos


class _Fuente:
    """Lista de dossiers que cambia cuando la prueba lo dice."""

    def __init__(self, items: list[dict]) -> None:
        self.items = items
        self.vivo = True
        self.lecturas_huella = 0
        self.lecturas_lista = 0

    async def huella(self) -> str | None:
        self.lecturas_huella += 1
        if not self.vivo:
            return None
        return json.dumps([i["id"] for i in self.items])

    async def lista(self) -> dict | None:
        self.lecturas_lista += 1
        if not self.vivo:
            return None
        return {"organization_id": "org", "items": list(self.items)}


def _frames(fuente: _Fuente, reloj: _Reloj, *, tope: int = 50, al_frame=None, **kw) -> list[str]:
    """Consume el generador; ``al_frame(i, frame)`` deja cambiar la fuente entre frames."""

    async def correr() -> list[str]:
        salida: list[str] = []
        gen = stream_dossier_list(
            fuente.huella,
            fuente.lista,
            check_seconds=kw.get("check", 5.0),
            heartbeat_seconds=kw.get("heartbeat", 15.0),
            max_seconds=kw.get("maximo", 600.0),
            sleep=reloj.dormir,
            clock=reloj,
        )
        async for frame in gen:
            salida.append(frame)
            if al_frame is not None:
                al_frame(len(salida) - 1, frame)
            if len(salida) >= tope:
                break
        return salida

    return asyncio.run(correr())


def _datos(frame: str) -> dict:
    linea = next(x for x in frame.splitlines() if x.startswith("data: "))
    return json.loads(linea.removeprefix("data: "))


def test_ca1_el_primer_evento_trae_la_lista_actual():
    fuente = _Fuente([{"id": "d1"}])
    frames = _frames(fuente, _Reloj(), maximo=0)
    assert len(frames) == 1
    assert frames[0].startswith("id: 1\nevent: dossiers\n")
    assert _datos(frames[0]) == {"organization_id": "org", "items": [{"id": "d1"}]}


def test_ca2_un_dossier_nuevo_llega_como_otro_evento():
    fuente = _Fuente([{"id": "d1"}])
    reloj = _Reloj()

    def al_frame(i: int, _frame: str) -> None:
        if i == 0:
            fuente.items = [{"id": "d2"}, {"id": "d1"}]

    frames = _frames(fuente, reloj, tope=2, al_frame=al_frame)
    assert [f.split("\n")[1] for f in frames] == ["event: dossiers", "event: dossiers"]
    assert _datos(frames[1])["items"] == [{"id": "d2"}, {"id": "d1"}]
    assert frames[1].startswith("id: 2\n")
    # Llegó en la primera comprobación, no al final de un sondeo largo.
    assert reloj.t == 5.0


def test_ca2_sin_cambios_solo_ping_y_no_relee_la_lista():
    fuente = _Fuente([{"id": "d1"}])
    reloj = _Reloj()
    frames = _frames(fuente, reloj, maximo=60.0)
    eventos = [f for f in frames if f.startswith("id:")]
    pings = [f for f in frames if f == ": ping\n\n"]
    assert len(eventos) == 1
    # 60 s con latido cada 15 s: a los 15, 30, 45 y 60 s.
    assert len(pings) == 4
    assert fuente.lecturas_lista == 1
    # Se comparó la huella en cada vuelta (cada 5 s), no la lista completa.
    assert fuente.lecturas_huella == 13


def test_ca4_si_la_huella_ya_no_es_valida_el_stream_termina():
    fuente = _Fuente([{"id": "d1"}])

    def al_frame(i: int, _frame: str) -> None:
        if i == 0:
            fuente.vivo = False

    frames = _frames(fuente, _Reloj(), al_frame=al_frame)
    assert len(frames) == 1


def test_sin_permiso_desde_el_inicio_no_envia_nada():
    fuente = _Fuente([{"id": "d1"}])
    fuente.vivo = False
    assert _frames(fuente, _Reloj()) == []


def test_ca5_termina_al_llegar_al_maximo():
    fuente = _Fuente([{"id": "d1"}])
    reloj = _Reloj()
    _frames(fuente, reloj, maximo=30.0)
    assert reloj.t == 30.0


def test_la_lista_cambia_entre_huella_y_lectura_no_repite_ni_pierde():
    """Si la lista cambia de nuevo, se envía otra vez; si no, no se repite."""
    fuente = _Fuente([{"id": "d1"}])
    cambios = iter([[{"id": "d2"}, {"id": "d1"}], [{"id": "d3"}, {"id": "d2"}, {"id": "d1"}]])

    def al_frame(i: int, frame: str) -> None:
        if frame.startswith("id:"):
            siguiente = next(cambios, None)
            if siguiente is not None:
                fuente.items = siguiente

    frames = _frames(fuente, _Reloj(), maximo=60.0, al_frame=al_frame)
    eventos = [_datos(f)["items"][0]["id"] for f in frames if f.startswith("id:")]
    assert eventos == ["d1", "d2", "d3"]


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(None, DEFAULT_CHECK_SECONDS), ("2", 2.0), ("0.2", 1.0), ("abc", DEFAULT_CHECK_SECONDS)],
)
def test_intervalo_de_comprobacion_configurable_con_minimo(monkeypatch, valor, esperado):
    if valor is None:
        monkeypatch.delenv("DOSSIER_NOTIFICATIONS_CHECK_SECONDS", raising=False)
    else:
        monkeypatch.setenv("DOSSIER_NOTIFICATIONS_CHECK_SECONDS", valor)
    assert check_seconds() == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(None, DEFAULT_MAX_SECONDS), ("0", 0.0), ("-5", 0.0), ("x", DEFAULT_MAX_SECONDS)],
)
def test_maximo_configurable(monkeypatch, valor, esperado):
    if valor is None:
        monkeypatch.delenv("DOSSIER_NOTIFICATIONS_MAX_SECONDS", raising=False)
    else:
        monkeypatch.setenv("DOSSIER_NOTIFICATIONS_MAX_SECONDS", valor)
    assert max_seconds() == esperado
