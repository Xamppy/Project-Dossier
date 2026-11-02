"""
Envío de correo por SMTP (S5.6). Pensado para Gmail con contraseña de aplicación
(``smtp.gmail.com:587`` + STARTTLS) y válido para cualquier servidor SMTP.

Una sola cuenta remitente por instancia, en variables de entorno: no se guarda ninguna
credencial en la base (actualización del ADR 0005, 2026-11-02). Se usa ``smtplib`` porque el
worker y las rutas que envían son síncronos.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
import unicodedata
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from email_validator import EmailNotValidError, validate_email

logger = logging.getLogger(__name__)

ASUNTO_MAXIMO = 200
ASUNTO_POR_OMISION = "Project Dossier"
# Gmail rechaza mensajes de más de 25 MB, y base64 suma un tercio: 18 MB de adjuntos es el techo.
ADJUNTOS_MAXIMO_BYTES = 18 * 1024 * 1024
_SEGURIDADES = ("starttls", "ssl", "none")


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes
    mime_type: str


class EmailNotConfiguredError(RuntimeError):
    """Faltan variables SMTP: el envío no está disponible en esta instancia."""


class EmailDeliveryError(RuntimeError):
    """El servidor SMTP rechazó o no respondió. El mensaje nunca lleva credenciales."""


@dataclass(frozen=True)
class _SmtpConfig:
    host: str
    port: int
    security: str
    username: str
    password: str
    from_email: str
    from_name: str
    timeout: float


def _config() -> _SmtpConfig:
    security = (os.getenv("SMTP_SECURITY") or "starttls").strip().lower()
    puerto_por_omision = 465 if security == "ssl" else 587
    try:
        port = int((os.getenv("SMTP_PORT") or "").strip() or puerto_por_omision)
    except ValueError:
        port = puerto_por_omision
    try:
        timeout = float((os.getenv("SMTP_TIMEOUT_SECONDS") or "").strip() or 20)
    except ValueError:
        timeout = 20.0
    username = (os.getenv("SMTP_USERNAME") or "").strip()
    # Google muestra la contraseña de aplicación en cuatro grupos separados por espacios.
    password = "".join((os.getenv("SMTP_PASSWORD") or "").split())
    return _SmtpConfig(
        host=(os.getenv("SMTP_HOST") or "smtp.gmail.com").strip(),
        port=port,
        security=security,
        username=username,
        password=password,
        from_email=(os.getenv("SMTP_FROM_EMAIL") or "").strip() or username,
        from_name=(os.getenv("SMTP_FROM_NAME") or "").strip() or "Project Dossier",
        timeout=timeout,
    )


def _configurada(cfg: _SmtpConfig) -> bool:
    if not cfg.host or not cfg.from_email or cfg.security not in _SEGURIDADES:
        return False
    # Sin TLS solo tiene sentido contra un servidor local de pruebas, que no pide login.
    return cfg.security == "none" or bool(cfg.username and cfg.password)


def email_delivery_available() -> bool:
    return _configurada(_config())


def _limpiar_asunto(asunto: str) -> str:
    sin_controles = "".join(
        " " if unicodedata.category(c).startswith("C") else c for c in asunto or ""
    )
    limpio = " ".join(sin_controles.split())[:ASUNTO_MAXIMO].strip()
    return limpio or ASUNTO_POR_OMISION


def _validar_destinatarios(to: list[str]) -> list[str]:
    if not to:
        raise ValueError("Falta el destinatario del correo.")
    validos: list[str] = []
    for direccion in to:
        if not isinstance(direccion, str) or any(c in direccion for c in "\r\n,;"):
            raise ValueError("Dirección de correo inválida.")
        try:
            validos.append(validate_email(direccion.strip(), check_deliverability=False).normalized)
        except EmailNotValidError as exc:
            raise ValueError("Dirección de correo inválida.") from exc
    return validos


def _validar_adjuntos(adjuntos: list[EmailAttachment]) -> None:
    if sum(len(a.content) for a in adjuntos) > ADJUNTOS_MAXIMO_BYTES:
        raise ValueError("Los adjuntos superan el tamaño máximo del correo.")
    for a in adjuntos:
        tipo, _, subtipo = a.mime_type.partition("/")
        if not tipo or not subtipo:
            raise ValueError("Tipo de adjunto inválido.")


def _nombre_adjunto(nombre: str) -> str:
    """Solo el nombre, en una línea: un cliente de correo no debe ver rutas ni cabeceras."""
    base = nombre.replace("\\", "/").rsplit("/", 1)[-1]
    return " ".join(_limpiar_asunto(base).split()) if base.strip() else "adjunto"


def _armar_mensaje(
    cfg: _SmtpConfig,
    to: list[str],
    subject: str,
    text: str,
    html: str,
    adjuntos: list[EmailAttachment],
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = _limpiar_asunto(subject)
    msg["From"] = formataddr((cfg.from_name, cfg.from_email))
    msg["To"] = ", ".join(to)
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=cfg.from_email.rpartition("@")[2] or None)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    for a in adjuntos:
        tipo, _, subtipo = a.mime_type.partition("/")
        msg.add_attachment(a.content, maintype=tipo, subtype=subtipo, filename=_nombre_adjunto(a.filename))
    return msg


def send_email(
    *,
    to: list[str],
    subject: str,
    text: str,
    html: str,
    attachments: list[EmailAttachment] | None = None,
) -> None:
    """Entrega texto + HTML (``multipart/alternative``) y, si hay adjuntos, los suma en un
    ``multipart/mixed``. Lanza un error claro si no puede."""
    destinatarios = _validar_destinatarios(to)
    adjuntos = list(attachments or [])
    _validar_adjuntos(adjuntos)
    cfg = _config()
    if not _configurada(cfg):
        raise EmailNotConfiguredError("El envío por correo no está configurado (SMTP_USERNAME / SMTP_PASSWORD).")
    msg = _armar_mensaje(cfg, destinatarios, subject, text, html, adjuntos)

    conexion: smtplib.SMTP
    try:
        if cfg.security == "ssl":
            conexion = smtplib.SMTP_SSL(
                cfg.host, cfg.port, timeout=cfg.timeout, context=ssl.create_default_context()
            )
        else:
            conexion = smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout)
        with conexion as smtp:
            smtp.ehlo()
            if cfg.security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if cfg.username and cfg.password:
                smtp.login(cfg.username, cfg.password)
            smtp.send_message(msg)
    # `from None`: la traza original de smtplib puede incluir el diálogo de autenticación.
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailDeliveryError(
            f"El servidor SMTP rechazó el usuario o la contraseña de aplicación ({exc.smtp_code})."
        ) from None
    except (smtplib.SMTPException, OSError) as exc:
        codigo = getattr(exc, "smtp_code", None)
        detalle = f"{type(exc).__name__}{f' {codigo}' if codigo else ''}"
        raise EmailDeliveryError(f"No se pudo enviar el correo ({detalle}).") from None

    logger.info("Correo enviado a %d destinatario(s) por %s:%s", len(destinatarios), cfg.host, cfg.port)
