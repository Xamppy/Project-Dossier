"""S6.6, unitarias: el evento de auditoría de un envío por correo (CA4).

Especificación: ``specs/proposals/S6.6-auditoria-correo-borrado.md``.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from dossier.services.dossier_email import evento_envio
from dossier.services.email_service import EmailDeliveryError

DESTINO = "ana.perez@cliente-prueba.example"


def _dossier():
    return SimpleNamespace(id=uuid.uuid4(), organization_id=uuid.uuid4(), requested_by_user_id=uuid.uuid4())


def test_envio_manual_exitoso():
    d = _dossier()
    usuario = uuid.uuid4()
    ev = evento_envio(d, manual=True, user_id=usuario)
    assert ev.action == "EMAIL dossier_manual"
    assert (ev.resource_type, ev.resource_id) == ("dossier", d.id)
    assert (ev.user_id, ev.organization_id) == (usuario, d.organization_id)
    assert ev.success is True
    assert ev.error_message is None


def test_envio_automatico_usa_a_quien_pidio_la_generacion():
    d = _dossier()
    ev = evento_envio(d, manual=False)
    assert ev.action == "EMAIL dossier_auto"
    assert ev.user_id == d.requested_by_user_id


def test_un_fallo_guarda_solo_la_clase_del_error():
    d = _dossier()
    error = EmailDeliveryError(f"550 buzón inexistente <{DESTINO}>")
    ev = evento_envio(d, manual=True, user_id=uuid.uuid4(), error=error)
    assert ev.success is False
    assert ev.error_message == "EmailDeliveryError"


def test_el_evento_no_lleva_el_destinatario():
    d = _dossier()
    ev = evento_envio(d, manual=True, user_id=uuid.uuid4(), error=EmailDeliveryError(DESTINO))
    assert DESTINO not in repr(ev)
