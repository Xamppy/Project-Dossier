"""S5.6 · Servicio SMTP (Gmail con contraseña de aplicación), sin red: ``smtplib`` es un doble.

Criterios CA1–CA6 de ``specs/proposals/S6.1-envio-dossier-correo.md``.
"""
from __future__ import annotations

import smtplib
import ssl
from typing import ClassVar

import pytest

from dossier.services import email_service
from dossier.services.email_service import (
    EmailDeliveryError,
    EmailNotConfiguredError,
    email_delivery_available,
    send_email,
)

CONTRASENA = "abcd efgh ijkl mnop"


class SmtpFalso:
    """Registra lo que haría ``smtplib.SMTP`` / ``SMTP_SSL`` sin abrir sockets."""

    instancias: ClassVar[list[SmtpFalso]] = []
    fallo_en: ClassVar[str | None] = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context_ssl = context
        self.pasos: list[str] = []
        self.login_args: tuple[str, str] | None = None
        self.starttls_context = None
        self.mensajes: list = []
        SmtpFalso.instancias.append(self)
        self._quizas_fallar("connect")

    def _quizas_fallar(self, paso: str) -> None:
        if SmtpFalso.fallo_en == paso:
            if paso == "login":
                raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
            if paso == "connect":
                raise TimeoutError("timed out")
            raise smtplib.SMTPRecipientsRefused({"x@example.com": (550, b"rechazado")})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.pasos.append("quit")
        return False

    def ehlo(self):
        self.pasos.append("ehlo")

    def starttls(self, context=None):
        self.pasos.append("starttls")
        self.starttls_context = context

    def login(self, user, password):
        self.pasos.append("login")
        self.login_args = (user, password)
        self._quizas_fallar("login")

    def send_message(self, msg):
        self.pasos.append("send")
        self._quizas_fallar("send")
        self.mensajes.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    SmtpFalso.instancias = []
    SmtpFalso.fallo_en = None
    monkeypatch.setattr(email_service.smtplib, "SMTP", SmtpFalso)
    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", SmtpFalso)
    return SmtpFalso


@pytest.fixture
def gmail(monkeypatch):
    for var in (
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_SECURITY",
        "SMTP_FROM_EMAIL",
        "SMTP_FROM_NAME",
        "SMTP_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SMTP_USERNAME", "remitente@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", CONTRASENA)


def _enviar(**extra):
    datos = {
        "to": ["destino@example.com"],
        "subject": "Dossier: Ana Prueba",
        "text": "Informe en texto",
        "html": "<p>Informe en HTML</p>",
    }
    datos.update(extra)
    send_email(**datos)


# --- CA1: Gmail por omisión, STARTTLS verificado, multipart ---


def test_envia_por_gmail_con_starttls_y_login(gmail, smtp):
    _enviar()

    (conexion,) = smtp.instancias
    assert (conexion.host, conexion.port) == ("smtp.gmail.com", 587)
    assert conexion.timeout == 20
    assert conexion.pasos == ["ehlo", "starttls", "ehlo", "login", "send", "quit"]
    assert isinstance(conexion.starttls_context, ssl.SSLContext)
    assert conexion.starttls_context.verify_mode == ssl.CERT_REQUIRED
    assert conexion.starttls_context.check_hostname is True


def test_el_mensaje_es_multipart_con_texto_y_html(gmail, smtp):
    _enviar()

    msg = smtp.instancias[0].mensajes[0]
    assert msg["To"] == "destino@example.com"
    assert msg["Subject"] == "Dossier: Ana Prueba"
    assert msg["From"] == "Project Dossier <remitente@gmail.com>"
    assert msg.get_content_type() == "multipart/alternative"
    partes = {p.get_content_type(): p.get_content() for p in msg.iter_parts()}
    assert partes["text/plain"].strip() == "Informe en texto"
    assert "<p>Informe en HTML</p>" in partes["text/html"]


def test_remitente_y_servidor_configurables(gmail, smtp, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "avisos@example.com")
    monkeypatch.setenv("SMTP_FROM_NAME", "Avisos")
    monkeypatch.setenv("SMTP_TIMEOUT_SECONDS", "5")

    _enviar()

    conexion = smtp.instancias[0]
    assert (conexion.host, conexion.port, conexion.timeout) == ("smtp.example.com", 2525, 5.0)
    assert conexion.mensajes[0]["From"] == "Avisos <avisos@example.com>"


def test_modo_ssl_usa_smtp_ssl_con_contexto_verificado(gmail, smtp, monkeypatch):
    monkeypatch.setenv("SMTP_SECURITY", "ssl")
    monkeypatch.setenv("SMTP_PORT", "465")

    _enviar()

    conexion = smtp.instancias[0]
    assert conexion.port == 465
    assert isinstance(conexion.context_ssl, ssl.SSLContext)
    assert "starttls" not in conexion.pasos


def test_modo_none_sin_credenciales_no_hace_login(smtp, monkeypatch):
    """Servidor local de pruebas (Mailpit): sin TLS y sin autenticación."""
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", "1025")
    monkeypatch.setenv("SMTP_SECURITY", "none")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "local@example.com")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    assert email_delivery_available() is True
    _enviar()

    assert smtp.instancias[0].pasos == ["ehlo", "send", "quit"]


def test_varios_destinatarios_en_un_solo_mensaje(gmail, smtp):
    _enviar(to=["a@example.com", "b@example.com"])

    assert smtp.instancias[0].mensajes[0]["To"] == "a@example.com, b@example.com"


# --- CA2: contraseña de aplicación con espacios ---


def test_la_contrasena_de_aplicacion_se_usa_sin_espacios(gmail, smtp):
    _enviar()

    assert smtp.instancias[0].login_args == ("remitente@gmail.com", "abcdefghijklmnop")


# --- CA3: sin configuración ---


@pytest.mark.parametrize("falta", ["SMTP_USERNAME", "SMTP_PASSWORD"])
def test_sin_credenciales_no_esta_disponible_ni_conecta(gmail, smtp, monkeypatch, falta):
    monkeypatch.delenv(falta)

    assert email_delivery_available() is False
    with pytest.raises(EmailNotConfiguredError):
        _enviar()
    assert smtp.instancias == []


def test_con_credenciales_esta_disponible(gmail):
    assert email_delivery_available() is True


def test_seguridad_desconocida_no_esta_disponible(gmail, smtp, monkeypatch):
    monkeypatch.setenv("SMTP_SECURITY", "tls-quizas")

    assert email_delivery_available() is False
    with pytest.raises(EmailNotConfiguredError):
        _enviar()


# --- CA4: errores del servidor ---


@pytest.mark.parametrize("paso", ["connect", "login", "send"])
def test_fallos_del_servidor_lanzan_email_delivery_error_sin_contrasena(gmail, smtp, paso):
    smtp.fallo_en = paso

    with pytest.raises(EmailDeliveryError) as exc:
        _enviar()

    texto = f"{exc.value} {exc.value!r} {exc.value.__cause__!r}"
    assert "abcd" not in texto
    assert "abcdefghijklmnop" not in str(exc.value)


def test_fallo_de_login_da_mensaje_util(gmail, smtp):
    smtp.fallo_en = "login"

    with pytest.raises(EmailDeliveryError, match="contraseña de aplicación"):
        _enviar()


# --- CA5: asunto en una sola línea ---


def test_asunto_con_saltos_y_controles_queda_en_una_linea(gmail, smtp):
    _enviar(subject="Dossier: Ana\r\nBcc: victima@example.com\x00\x07")

    msg = smtp.instancias[0].mensajes[0]
    assert msg["Bcc"] is None
    assert "\n" not in msg["Subject"] and "\r" not in msg["Subject"]
    assert msg["Subject"] == "Dossier: Ana Bcc: victima@example.com"


def test_asunto_largo_se_corta_a_200(gmail, smtp):
    _enviar(subject="x" * 500)

    assert len(smtp.instancias[0].mensajes[0]["Subject"]) == 200


def test_asunto_vacio_usa_uno_por_omision(gmail, smtp):
    _enviar(subject="  \r\n ")

    assert smtp.instancias[0].mensajes[0]["Subject"] == "Project Dossier"


# --- CA6: destinatarios inválidos ---


@pytest.mark.parametrize(
    "destino",
    [
        [],
        ["no-es-correo"],
        ["a@example.com\r\nBcc: b@example.com"],
        ["a@example.com, b@example.com"],
        [""],
    ],
)
def test_destinatarios_invalidos_no_abren_conexion(gmail, smtp, destino):
    with pytest.raises(ValueError):
        _enviar(to=destino)
    assert smtp.instancias == []
