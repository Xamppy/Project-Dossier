"""UX-CAL-03 · CA7: la persona del dossier la decide el servidor con los datos de la reunión.

El cuerpo de la petición trae una copia de la reunión que el cliente podría alterar. Cuando hay
``event_id`` manda el evento leído del proveedor, y la elección nunca viaja dentro de ``reunion``.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from dossier.api import app as app_pkg  # noqa: F401 - registra el módulo
from dossier.services import graph_calendar as graph

REAL = {
    "id": "ev-1", "tema": "Avance", "descripcion": "", "participantes": "", "inicio": "", "fin": "",
    "ubicacion": "", "todo_el_dia": False,
    "asistentes": [
        {"nombre": None, "correo": "ana@acme.test", "yo": False},
        {"nombre": None, "correo": "max@acme.test", "yo": False},
    ],
}


@pytest.fixture
def modulo(monkeypatch):
    import sys

    m = sys.modules["dossier.api.app"]
    monkeypatch.setattr(m, "obtener_reunion_google_por_id", lambda tok, eid: REAL)
    monkeypatch.setattr(m, "_integracion_de_calendario", lambda db, user_id, provider: None)
    return m


def _pedir(m, *, reunion, persona_id):
    reuniones = m._resolve_google_reuniones("tok", event_id="ev-1", reunion_payload=reunion, top=5)
    return m._exigir_una_persona(
        None, user=SimpleNamespace(id="u", email="yo@x.test"), calendar_provider="google",
        reuniones=reuniones, persona_id=persona_id, una_reunion=True,
    )


def test_un_asistente_inyectado_en_el_cuerpo_no_se_puede_elegir(modulo):
    falsa = {**REAL, "asistentes": [{"nombre": "Víctima", "correo": "victima@otra.test", "yo": False}]}
    with pytest.raises(HTTPException) as exc:
        _pedir(modulo, reunion=falsa, persona_id="victima@otra.test")
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "CALENDAR_PERSON_NOT_FOUND"
    assert "victima@otra.test" not in str(exc.value.detail)


def test_la_eleccion_dentro_de_reunion_se_ignora(modulo):
    falsa = {**REAL, "_persona_elegida": {"full_name": "Víctima", "email": "victima@otra.test"}}
    with pytest.raises(HTTPException) as exc:
        _pedir(modulo, reunion=falsa, persona_id=None)
    assert exc.value.detail["code"] == "CALENDAR_PERSON_REQUIRED"
    (elegida,) = _pedir(modulo, reunion=falsa, persona_id="max@acme.test")
    assert elegida["_persona_elegida"]["email"] == "max@acme.test"


def test_ocultar_asistentes_en_el_cuerpo_no_evita_elegir(modulo):
    with pytest.raises(HTTPException):
        _pedir(modulo, reunion={**REAL, "asistentes": []}, persona_id=None)


def test_la_lista_que_envia_el_cliente_se_acota():
    muchos = [{"nombre": "N" * 5000, "correo": f"p{i}@acme.test", "yo": False} for i in range(5000)]
    limpio = graph.coerce_reunion_payload({"id": "x", "tema": "y", "asistentes": muchos})
    assert len(limpio["asistentes"]) <= 500
    assert all(len(a["nombre"]) <= 255 for a in limpio["asistentes"])
