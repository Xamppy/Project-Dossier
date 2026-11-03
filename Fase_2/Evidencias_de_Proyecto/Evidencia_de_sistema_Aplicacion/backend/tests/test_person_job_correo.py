"""S6.1 · Envío automático del dossier de Personas a quien lo pidió, sin base ni red.

Desde el 2026-11-02 (tarde) el envío no se pide: sale siempre que la instancia tenga SMTP.
CA10–CA12 de punta a punta están en ``tests/integration/test_person_job_correo_integracion.py``.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from dossier.schemas.person_research import PersonResearchRequest
from dossier.services import dossier_generation_job_service as servicio

USUARIO = SimpleNamespace(id=uuid.uuid4(), email="ana@example.com")


@pytest.fixture
def entregas(monkeypatch):
    llamadas: list[dict] = []

    def entregar(db, *, dossier_id, recipient):
        llamadas.append({"dossier_id": dossier_id, "recipient": recipient})
        return True

    monkeypatch.setattr(servicio, "deliver_dossier_after_generation", entregar)
    monkeypatch.setattr(servicio, "email_delivery_available", lambda: True)
    return llamadas


def _resultado(status="complete", dossier_id="d-1") -> dict:
    return {"saved_dossier": {"id": dossier_id, "status": status}}


def test_dossier_completo_se_envia_al_solicitante_sin_pedirlo(entregas):
    servicio.enviar_dossier_al_solicitante(object(), result=_resultado(), user=USUARIO)

    assert entregas == [{"dossier_id": "d-1", "recipient": "ana@example.com"}]


def test_la_peticion_ya_no_tiene_send_email():
    assert "send_email" not in PersonResearchRequest.model_fields


@pytest.mark.parametrize(
    "resultado",
    [_resultado(status="failed"), {"saved_dossier": None}, {}, _resultado(dossier_id=None)],
    ids=["dossier_fallido", "sin_guardar", "sin_resultado", "sin_id"],
)
def test_sin_dossier_completo_no_se_envia(entregas, resultado):
    servicio.enviar_dossier_al_solicitante(object(), result=resultado, user=USUARIO)

    assert entregas == []


def test_usuario_sin_correo_no_intenta_enviar(entregas):
    sin_correo = SimpleNamespace(id=uuid.uuid4(), email="")

    servicio.enviar_dossier_al_solicitante(object(), result=_resultado(), user=sin_correo)

    assert entregas == []


def test_sin_smtp_configurado_no_intenta_enviar(entregas, monkeypatch):
    monkeypatch.setattr(servicio, "email_delivery_available", lambda: False)

    servicio.enviar_dossier_al_solicitante(object(), result=_resultado(), user=USUARIO)

    assert entregas == []
