"""UX-CAL-03 · estrés: una reunión enorme y un mes entero de reuniones se resuelven rápido."""
from __future__ import annotations

import time

from dossier.services.meeting_people import personas_de_la_reunion


def _reunion(n: int) -> dict:
    contactos = "\n".join(f"Contacto {i}: Persona Numero{i}" for i in range(1, 21))
    return {
        "tema": "Asamblea",
        "descripcion": contactos,
        "asistentes": [{"nombre": None, "correo": f"persona.n{i}@acme.test", "yo": False} for i in range(n)],
    }


def test_volumen_una_reunion_con_quinientos_asistentes():
    t0 = time.perf_counter()
    personas = personas_de_la_reunion(_reunion(500), set())
    assert time.perf_counter() - t0 < 2
    assert len(personas) == 520
    assert len({p["id"] for p in personas}) == 520


def test_volumen_mil_reuniones_de_diez_asistentes():
    reunion = _reunion(10)
    t0 = time.perf_counter()
    for _ in range(1000):
        personas_de_la_reunion(reunion, set())
    assert time.perf_counter() - t0 < 10
