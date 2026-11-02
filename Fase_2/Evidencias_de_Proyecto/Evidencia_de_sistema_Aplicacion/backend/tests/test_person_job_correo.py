"""S6.1 · Gancho del envío automático en los jobs de Personas, sin base ni red.

CA10–CA12 de punta a punta están en ``tests/integration/test_person_job_correo_integracion.py``.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from dossier.schemas.person_research import PersonResearchRequest
from dossier.services import dossier_generation_job_service as servicio
from dossier.services.person_dossier_dedup import person_research_fingerprint

USUARIO = SimpleNamespace(id=uuid.uuid4(), email="ana@example.com")


@pytest.fixture
def entregas(monkeypatch):
    llamadas: list[dict] = []

    def entregar(db, *, dossier_id, recipient):
        llamadas.append({"dossier_id": dossier_id, "recipient": recipient})
        return True

    monkeypatch.setattr(servicio, "deliver_dossier_after_generation", entregar)
    return llamadas


def _pedido(**extra) -> PersonResearchRequest:
    return PersonResearchRequest(full_name="Ana Prueba", **extra)


def _resultado(status="complete", dossier_id="d-1") -> dict:
    return {"saved_dossier": {"id": dossier_id, "status": status}}


def test_send_email_es_falso_por_omision():
    assert _pedido().send_email is False


def test_send_email_no_cambia_la_huella_de_deduplicacion():
    org = uuid.uuid4()
    assert person_research_fingerprint(_pedido(), org) == person_research_fingerprint(
        _pedido(send_email=True), org
    )


def test_con_send_email_y_dossier_completo_se_envia_al_solicitante(entregas):
    servicio.enviar_por_correo_si_se_pidio(
        object(), body=_pedido(send_email=True), result=_resultado(), user=USUARIO
    )

    assert entregas == [{"dossier_id": "d-1", "recipient": "ana@example.com"}]


@pytest.mark.parametrize(
    ("pedido", "resultado"),
    [
        (_pedido(), _resultado()),
        (_pedido(send_email=True), _resultado(status="failed")),
        (_pedido(send_email=True), {"saved_dossier": None}),
        (_pedido(send_email=True), {}),
        (_pedido(send_email=True), _resultado(dossier_id=None)),
    ],
    ids=["sin_pedirlo", "dossier_fallido", "sin_guardar", "sin_resultado", "sin_id"],
)
def test_sin_pedirlo_o_sin_dossier_completo_no_se_envia(entregas, pedido, resultado):
    servicio.enviar_por_correo_si_se_pidio(object(), body=pedido, result=resultado, user=USUARIO)

    assert entregas == []


def test_usuario_sin_correo_no_intenta_enviar(entregas):
    sin_correo = SimpleNamespace(id=uuid.uuid4(), email="")

    servicio.enviar_por_correo_si_se_pidio(
        object(), body=_pedido(send_email=True), result=_resultado(), user=sin_correo
    )

    assert entregas == []
