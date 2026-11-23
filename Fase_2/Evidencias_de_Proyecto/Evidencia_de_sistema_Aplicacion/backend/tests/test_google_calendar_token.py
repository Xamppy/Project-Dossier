"""Renovación del token de Google Calendar cuando Google rechaza el ``refresh_token``.

Si Google responde ``invalid_grant`` el token ya no sirve (vencido, revocado o
emitido para otro cliente OAuth): reintentar solo llena los logs. La integración
queda marcada para reconectar y el sync deja de llamar a Google hasta que el
usuario vuelva a conectar. Los errores pasajeros o de configuración del servidor
no tocan la integración.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from dossier.db.models import CalendarIntegration
from dossier.services import calendar_automation
from dossier.services import google_calendar_token as gct


class _Respuesta:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> dict:
        return self._body


def _integracion_vencida() -> CalendarIntegration:
    return CalendarIntegration(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        provider="google",
        is_enabled=True,
        revoked_at=None,
        access_token_encrypted="access-viejo",
        refresh_token_encrypted="refresh-muerto",
        access_token_expires_at=datetime.now(UTC) - timedelta(hours=1),
    )


def _db_con(row: CalendarIntegration) -> MagicMock:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = row
    return db


@pytest.fixture(autouse=True)
def _credenciales(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cliente-prueba")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secreto-prueba")


def _google_responde(monkeypatch, status_code: int, body: dict) -> MagicMock:
    post = MagicMock(return_value=_Respuesta(status_code, body))
    monkeypatch.setattr(gct.requests, "post", post)
    return post


def test_invalid_grant_marca_la_integracion_para_reconectar(monkeypatch):
    row = _integracion_vencida()
    db = _db_con(row)
    _google_responde(monkeypatch, 400, {"error": "invalid_grant", "error_description": "Bad Request"})

    with pytest.raises(HTTPException) as exc:
        gct.get_google_calendar_access_token_for_user(db, row.user_id)

    assert exc.value.status_code == 401
    assert "Vuelve a conectar" in exc.value.detail
    assert row.revoked_at is not None
    assert row.is_enabled is False
    assert row.access_token_encrypted is None
    assert row.refresh_token_encrypted is None
    db.commit.assert_called_once()


def test_el_log_incluye_el_codigo_de_error_de_google(monkeypatch, caplog):
    row = _integracion_vencida()
    _google_responde(monkeypatch, 400, {"error": "invalid_grant", "error_description": "Bad Request"})

    with caplog.at_level(logging.WARNING, logger=gct.__name__), pytest.raises(HTTPException):
        gct.get_google_calendar_access_token_for_user(_db_con(row), row.user_id)

    assert "invalid_grant" in caplog.text


def test_tras_invalid_grant_el_sync_no_vuelve_a_llamar_a_google(monkeypatch):
    row = _integracion_vencida()
    db = _db_con(row)
    post = _google_responde(
        monkeypatch, 400, {"error": "invalid_grant", "error_description": "Bad Request"}
    )

    assert calendar_automation.sync_calendar_events_for_integration(db, row) == 0
    assert calendar_automation.sync_calendar_events_for_integration(db, row) == 0
    assert calendar_automation.sync_calendar_events_for_integration(db, row) == 0

    assert post.call_count == 1


@pytest.mark.parametrize(
    ("status_code", "body"),
    [
        (500, {"error": "internal_failure"}),
        (401, {"error": "invalid_client", "error_description": "Unauthorized"}),
        (400, {"error": "invalid_request"}),
    ],
)
def test_otros_errores_no_tocan_la_integracion(monkeypatch, status_code, body):
    row = _integracion_vencida()
    db = _db_con(row)
    _google_responde(monkeypatch, status_code, body)

    with pytest.raises(HTTPException) as exc:
        gct.get_google_calendar_access_token_for_user(db, row.user_id)

    assert exc.value.status_code == 401
    assert row.revoked_at is None
    assert row.is_enabled is True
    assert row.refresh_token_encrypted == "refresh-muerto"
    db.commit.assert_not_called()
