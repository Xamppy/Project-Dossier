"""S6.4, unitarias: fallos pasajeros y definitivos, y los intentos seguidos (CA1, CA2).

Especificación: ``specs/proposals/S6.4-reintento-correo.md``. Sin esperas reales.
"""
from __future__ import annotations

import smtplib
import socket

import pytest

from dossier.services.dossier_email_retry import enviar_con_reintentos
from dossier.services.email_service import EmailDeliveryError, error_transitorio, send_email

# --------------------------------------------------------------------------
# CA1 · qué es pasajero y qué es definitivo
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        ConnectionRefusedError(),
        TimeoutError(),
        smtplib.SMTPServerDisconnected("se cortó"),
        smtplib.SMTPResponseException(421, b"servicio no disponible"),
        smtplib.SMTPDataError(451, b"intenta luego"),
        smtplib.SMTPRecipientsRefused({"a@x.example": (450, b"buzon ocupado")}),
    ],
)
def test_fallos_pasajeros(error):
    assert error_transitorio(error) is True


@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPResponseException(554, b"rechazado"),
        smtplib.SMTPDataError(552, b"muy grande"),
        smtplib.SMTPRecipientsRefused({"a@x.example": (550, b"no existe")}),
        smtplib.SMTPAuthenticationError(535, b"credenciales"),
    ],
)
def test_fallos_definitivos(error):
    assert error_transitorio(error) is False


def _puerto_cerrado() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_send_email_marca_como_pasajero_un_servidor_que_no_contesta(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", str(_puerto_cerrado()))
    monkeypatch.setenv("SMTP_SECURITY", "none")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "dossier@example.com")
    monkeypatch.setenv("SMTP_TIMEOUT_SECONDS", "2")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    with pytest.raises(EmailDeliveryError) as info:
        send_email(to=["ana@example.com"], subject="s", text="t", html="<p>t</p>")
    assert info.value.transitorio is True


# --------------------------------------------------------------------------
# CA2 · tres intentos seguidos con esperas de 2 s y 5 s
# --------------------------------------------------------------------------


class _Envio:
    def __init__(self, fallos: list[Exception]):
        self.fallos = list(fallos)
        self.llamadas = 0

    def __call__(self):
        self.llamadas += 1
        if self.fallos:
            raise self.fallos.pop(0)


def _pasajero():
    return EmailDeliveryError("sin conexión", transitorio=True)


def test_un_fallo_pasajero_se_reintenta_hasta_que_sale():
    esperas: list[float] = []
    envio = _Envio([_pasajero(), _pasajero()])

    resultado = enviar_con_reintentos(envio, dormir=esperas.append)

    assert resultado.error is None
    assert resultado.intentos == 3
    assert esperas == [2.0, 5.0]


def test_tres_fallos_pasajeros_devuelven_el_ultimo_error():
    esperas: list[float] = []
    envio = _Envio([_pasajero(), _pasajero(), _pasajero()])

    resultado = enviar_con_reintentos(envio, dormir=esperas.append)

    assert isinstance(resultado.error, EmailDeliveryError)
    assert resultado.intentos == 3
    assert envio.llamadas == 3
    assert esperas == [2.0, 5.0]


def test_un_fallo_definitivo_no_se_reintenta():
    esperas: list[float] = []
    envio = _Envio([EmailDeliveryError("550", transitorio=False)])

    resultado = enviar_con_reintentos(envio, dormir=esperas.append)

    assert resultado.intentos == 1
    assert envio.llamadas == 1
    assert esperas == []


def test_un_error_que_no_es_de_correo_no_se_reintenta():
    envio = _Envio([ValueError("dossier vacío")])
    resultado = enviar_con_reintentos(envio, dormir=lambda _s: None)
    assert resultado.intentos == 1
    assert isinstance(resultado.error, ValueError)


def test_el_primer_intento_exitoso_no_espera():
    esperas: list[float] = []
    resultado = enviar_con_reintentos(_Envio([]), dormir=esperas.append)
    assert (resultado.intentos, resultado.error, esperas) == (1, None, [])
