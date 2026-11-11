"""
Correo del dossier (S5.7) y su envío con registro en ``dossiers`` (S6.1).

El correo es una confirmación con un botón al dossier y el PDF completo adjunto
(``dossier_pdf``). Solo si el PDF no se puede generar, el informe (``dossier_data.body``) va en
el cuerpo, convertido de Markdown a HTML. El HTML crudo del informe se escapa: viene del LLM y
de fuentes externas, y en un correo no hay CSP que lo contenga.
"""
from __future__ import annotations

import html
import logging
import math
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from markdown_it import MarkdownIt
from sqlalchemy import select
from sqlalchemy.orm import Session

from dossier.db.models import Dossier
from dossier.services.audit_log import AuditEvent, record
from dossier.services.dossier_access_links import url_de_acceso_o_nada, vigencia_horas
from dossier.services.dossier_email_retry import (
    ResultadoIntentos,
    encolar_reintento,
    enviar_con_reintentos,
)
from dossier.services.dossier_pdf import dossier_pdf_filename, render_dossier_pdf
from dossier.services.email_service import EmailAttachment, EmailDeliveryError, send_email
from dossier.services.output_language import normalize_output_language
from dossier.utils.html_text import strip_html_to_plain_line

logger = logging.getLogger(__name__)

# Entre dos envíos manuales del mismo dossier: frena el doble clic y el abuso de la cuota de Gmail.
REENVIO_MINIMO_SEGUNDOS = 60

# commonmark + tablas y tachado (lo que usa el informe). Sin HTML crudo; markdown-it ya descarta
# los enlaces javascript:, vbscript: y data: (salvo imágenes data: de tipo gif/png/jpeg/webp).
_MARKDOWN = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])

_TEXTOS: dict[str, dict[str, str]] = {
    "es": {
        "untitled": "Sin nombre",
        "ready": "Tu dossier está listo",
        "intro": "Este es el dossier completo de {name} generado en Project Dossier.",
        "open": "Abrir en Project Dossier",
        "attached": "Adjuntamos el dossier en PDF para que lo consultes sin entrar a la plataforma.",
        "footer": (
            "Este correo contiene información confidencial sobre una persona. "
            "No lo reenvíes fuera de tu organización."
        ),
        "access_note": "El botón sirve una vez y vence en {hours} horas. Después, ábrelo desde el dashboard:",
    },
    "en": {
        "untitled": "Untitled",
        "ready": "Your dossier is ready",
        "intro": "This is the complete dossier on {name} generated in Project Dossier.",
        "open": "Open in Project Dossier",
        "attached": "The dossier is attached as a PDF so you can read it without signing in.",
        "footer": (
            "This email contains confidential information about a person. "
            "Do not forward it outside your organization."
        ),
        "access_note": "The button works once and expires in {hours} hours. After that, open it from the dashboard:",
    },
    "pt": {
        "untitled": "Sem nome",
        "ready": "O seu dossiê está pronto",
        "intro": "Este é o dossiê completo de {name} gerado no Project Dossier.",
        "open": "Abrir no Project Dossier",
        "attached": "Segue em anexo o dossiê em PDF para o consultar sem entrar na plataforma.",
        "footer": (
            "Este e-mail contém informação confidencial sobre uma pessoa. "
            "Não o reencaminhe para fora da sua organização."
        ),
        "access_note": "O botão funciona uma vez e expira em {hours} horas. Depois, abra-o a partir do painel:",
    },
    "it": {
        "untitled": "Senza nome",
        "ready": "Il tuo dossier è pronto",
        "intro": "Questo è il dossier completo su {name} generato in Project Dossier.",
        "open": "Apri in Project Dossier",
        "attached": "In allegato trovi il dossier in PDF da consultare senza accedere alla piattaforma.",
        "footer": (
            "Questa email contiene informazioni riservate su una persona. "
            "Non inoltrarla al di fuori della tua organizzazione."
        ),
        "access_note": "Il pulsante funziona una sola volta e scade tra {hours} ore. Dopo, aprilo dalla dashboard:",
    },
    "fr": {
        "untitled": "Sans nom",
        "ready": "Votre dossier est prêt",
        "intro": "Voici le dossier complet sur {name} généré dans Project Dossier.",
        "open": "Ouvrir dans Project Dossier",
        "attached": "Le dossier est joint en PDF pour le consulter sans vous connecter.",
        "footer": (
            "Cet e-mail contient des informations confidentielles sur une personne. "
            "Ne le transférez pas en dehors de votre organisation."
        ),
        "access_note": "Le bouton fonctionne une seule fois et expire dans {hours} heures. Ensuite, ouvrez-le depuis le tableau de bord :",
    },
    "de": {
        "untitled": "Ohne Namen",
        "ready": "Ihr Dossier ist fertig",
        "intro": "Dies ist das vollständige Dossier zu {name}, erstellt in Project Dossier.",
        "open": "In Project Dossier öffnen",
        "attached": "Das Dossier ist als PDF angehängt, damit Sie es ohne Anmeldung lesen können.",
        "footer": (
            "Diese E-Mail enthält vertrauliche Informationen über eine Person. "
            "Leiten Sie sie nicht außerhalb Ihrer Organisation weiter."
        ),
        "access_note": "Die Schaltfläche funktioniert einmal und läuft in {hours} Stunden ab. Danach öffnen Sie es im Dashboard:",
    },
}

# S6.3: el correo único con los dossiers de una reunión del calendario.
_TEXTOS_REUNION: dict[str, dict[str, str]] = {
    "es": {
        "untitled": "tu reunión",
        "ready": "Tus dossiers para la reunión están listos",
        "intro": "Estos son los dossiers de «{meeting}» generados en Project Dossier:",
        "attached": "Adjuntamos cada dossier en PDF para que los consultes sin entrar a la plataforma.",
        "access_note": "Cada enlace sirve una vez y vence en {hours} horas. Después, ábrelos desde el dashboard:",
    },
    "en": {
        "untitled": "your meeting",
        "ready": "Your meeting dossiers are ready",
        "intro": "These are the dossiers for “{meeting}” generated in Project Dossier:",
        "attached": "Each dossier is attached as a PDF so you can read them without signing in.",
        "access_note": "Each link works once and expires in {hours} hours. After that, open them from the dashboard:",
    },
    "pt": {
        "untitled": "a sua reunião",
        "ready": "Os dossiês da sua reunião estão prontos",
        "intro": "Estes são os dossiês de «{meeting}» gerados no Project Dossier:",
        "attached": "Segue cada dossiê em PDF para os consultar sem entrar na plataforma.",
        "access_note": "Cada link funciona uma vez e expira em {hours} horas. Depois, abra-os a partir do painel:",
    },
    "it": {
        "untitled": "la tua riunione",
        "ready": "I dossier per la tua riunione sono pronti",
        "intro": "Questi sono i dossier di «{meeting}» generati in Project Dossier:",
        "attached": "In allegato trovi ogni dossier in PDF da consultare senza accedere alla piattaforma.",
        "access_note": "Ogni link funziona una sola volta e scade tra {hours} ore. Dopo, aprili dalla dashboard:",
    },
    "fr": {
        "untitled": "votre réunion",
        "ready": "Les dossiers de votre réunion sont prêts",
        "intro": "Voici les dossiers de « {meeting} » générés dans Project Dossier :",
        "attached": "Chaque dossier est joint en PDF pour le consulter sans vous connecter.",
        "access_note": "Chaque lien fonctionne une seule fois et expire dans {hours} heures. Ensuite, ouvrez-les depuis le tableau de bord :",
    },
    "de": {
        "untitled": "Ihr Meeting",
        "ready": "Die Dossiers für Ihr Meeting sind fertig",
        "intro": "Dies sind die Dossiers zu „{meeting}“, erstellt in Project Dossier:",
        "attached": "Jedes Dossier ist als PDF angehängt, damit Sie es ohne Anmeldung lesen können.",
        "access_note": "Jeder Link funktioniert einmal und läuft in {hours} Stunden ab. Danach öffnen Sie sie im Dashboard:",
    },
}

# Los clientes de correo ignoran buena parte del CSS; esto es lo que Gmail y Outlook respetan.
_ESTILOS = """
body{margin:0;padding:0;background:#f4f5f7;font-family:Arial,Helvetica,sans-serif;color:#1f2937;}
.contenedor{max-width:720px;margin:0 auto;padding:24px 16px;}
.tarjeta{background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:24px;}
.informe{font-size:14px;line-height:1.6;}
.informe h1,.informe h2,.informe h3{color:#111827;line-height:1.3;}
.informe table{border-collapse:collapse;width:100%;margin:12px 0;}
.informe th,.informe td{border:1px solid #d1d5db;padding:6px 8px;text-align:left;vertical-align:top;}
.informe th{background:#f9fafb;}
.informe a{color:#4f46e5;}
.boton{display:inline-block;background:#4f46e5;color:#ffffff !important;text-decoration:none;
padding:10px 18px;border-radius:6px;font-weight:bold;}
.pie{font-size:12px;color:#6b7280;margin-top:16px;}
"""


@dataclass(frozen=True)
class DossierEmail:
    subject: str
    text: str
    html: str
    attachments: tuple[EmailAttachment, ...] = ()


def _frontend_base_url() -> str:
    return (os.getenv("DOSSIER_FRONTEND_URL") or os.getenv("FRONTEND_URL") or "http://localhost:3000").rstrip("/")


def dossier_detail_url(dossier_id: UUID) -> str:
    return f"{_frontend_base_url()}/dashboard/dossiers/{dossier_id}"


def _cuerpo(dossier: Dossier) -> str:
    data = dossier.dossier_data
    body = data.get("body") if isinstance(data, dict) else None
    if not isinstance(body, str) or not body.strip():
        raise ValueError("El dossier no tiene contenido para enviar.")
    return body.strip()


def _idioma(dossier: Dossier, language: str | None) -> str:
    if not language and isinstance(dossier.dossier_data, dict):
        language = dossier.dossier_data.get("output_language")
    return normalize_output_language(language)


def _nota_de_acceso(plantilla: str, panel_url: str) -> tuple[str, str]:
    """S6.2: la nota bajo el botón de un solo uso, en texto y en HTML, con el enlace al dashboard."""
    nota = plantilla.format(hours=vigencia_horas())
    html_nota = (
        f'<p style="margin:12px 0 0;font-size:13px;color:#4b5563;">{html.escape(nota)} '
        f'<a href="{html.escape(panel_url, quote=True)}">{html.escape(panel_url)}</a></p>\n'
    )
    return f"{nota} {panel_url}", html_nota


def build_dossier_email(
    dossier: Dossier, *, language: str | None, dossier_url: str, access_url: str | None = None
) -> DossierEmail:
    """Correo de un dossier. Con ``access_url`` (S6.2) el botón usa el enlace de un solo uso y
    debajo va el enlace al dashboard (``dossier_url``)."""
    body = _cuerpo(dossier)
    lang = _idioma(dossier, language)
    t = _TEXTOS[lang]
    nombre = strip_html_to_plain_line(dossier.subject_name, max_len=255) or t["untitled"]
    intro = t["intro"].format(name=nombre)
    adjuntos = _pdf_adjunto(dossier, lang)
    nota = [t["attached"]] if adjuntos else []
    boton_url = access_url or dossier_url
    acceso_texto, acceso_html = _nota_de_acceso(t["access_note"], dossier_url) if access_url else ("", "")

    # Con el PDF adjunto el correo es solo la confirmación y el botón (revisión de DG): el informe
    # va en el cuerpo únicamente si el PDF no se pudo generar, para que nunca llegue vacío.
    informe_texto = [] if adjuntos else ["-" * 40, body, "-" * 40]
    acceso = [acceso_texto] if acceso_texto else []
    text = "\n\n".join(
        [t["ready"], intro, *nota, f"{t['open']}: {boton_url}", *acceso, *informe_texto, t["footer"]]
    )
    nota_html = f'<p style="margin:0 0 16px;">{html.escape(nota[0])}</p>\n' if nota else ""
    informe_html = "" if adjuntos else (
        '<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0 16px;">\n'
        f'<div class="informe">\n{_MARKDOWN.render(body)}\n</div>\n'
    )
    html_doc = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(nombre)}</title>
<style>{_ESTILOS}</style>
</head>
<body>
<div class="contenedor">
<div class="tarjeta">
<p style="font-size:18px;font-weight:bold;margin:0 0 8px;">{html.escape(t["ready"])}</p>
<p style="margin:0 0 16px;">{html.escape(intro)}</p>
{nota_html}<p style="margin:0;"><a class="boton" href="{html.escape(boton_url, quote=True)}">{html.escape(t["open"])}</a></p>
{acceso_html}{informe_html}</div>
<p class="pie">{html.escape(t["footer"])}</p>
</div>
</body>
</html>
"""
    return DossierEmail(subject=f"Dossier: {nombre}", text=text, html=html_doc, attachments=adjuntos)


def build_meeting_email(
    dossiers: Sequence[Dossier],
    *,
    meeting_title: str | None,
    language: str | None,
    url_for: Callable[[UUID], str] = dossier_detail_url,
    access_for: Callable[[Dossier], str] | None = None,
) -> DossierEmail:
    """Un solo correo con todos los dossiers de una reunión (S6.3).

    Lleva el PDF de cada uno; el informe de un dossier cuyo PDF falló va en el cuerpo, como en
    ``build_dossier_email``. Con ``access_for`` (S6.2) cada nombre lleva su enlace de un solo uso
    y debajo va el enlace a la lista del dashboard.
    """
    if not dossiers:
        raise ValueError("No hay dossiers para enviar.")
    lang = _idioma(dossiers[0], language)
    t, r = _TEXTOS[lang], _TEXTOS_REUNION[lang]
    titulo = strip_html_to_plain_line(meeting_title, max_len=200) or r["untitled"]

    filas: list[tuple[str, str]] = []
    sin_pdf: list[tuple[str, str]] = []
    adjuntos: list[EmailAttachment] = []
    for dossier in dossiers:
        body = _cuerpo(dossier)
        nombre = strip_html_to_plain_line(dossier.subject_name, max_len=255) or t["untitled"]
        filas.append((nombre, access_for(dossier) if access_for else url_for(dossier.id)))
        pdf = _pdf_adjunto(dossier, lang)
        if pdf:
            adjuntos.extend(pdf)
        else:
            sin_pdf.append((nombre, body))

    intro = r["intro"].format(meeting=titulo)
    nota = [r["attached"]] if adjuntos else []
    lista_texto = "\n".join(f"- {nombre}: {url}" for nombre, url in filas)
    informes_texto = ["\n\n".join(["-" * 40, nombre, body, "-" * 40]) for nombre, body in sin_pdf]
    acceso_texto, acceso_html = (
        _nota_de_acceso(r["access_note"], f"{_frontend_base_url()}/dashboard/dossiers") if access_for else ("", "")
    )
    acceso = [acceso_texto] if acceso_texto else []
    text = "\n\n".join([r["ready"], intro, lista_texto, *acceso, *nota, *informes_texto, t["footer"]])

    lista_html = "".join(
        f'<li style="margin:0 0 6px;"><a href="{html.escape(url, quote=True)}">{html.escape(nombre)}</a></li>'
        for nombre, url in filas
    )
    nota_html = f'<p style="margin:16px 0 0;">{html.escape(nota[0])}</p>\n' if nota else ""
    informes_html = "".join(
        '<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0 16px;">\n'
        f'<p style="font-weight:bold;margin:0 0 8px;">{html.escape(nombre)}</p>\n'
        f'<div class="informe">\n{_MARKDOWN.render(body)}\n</div>\n'
        for nombre, body in sin_pdf
    )
    html_doc = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)}</title>
<style>{_ESTILOS}</style>
</head>
<body>
<div class="contenedor">
<div class="tarjeta">
<p style="font-size:18px;font-weight:bold;margin:0 0 8px;">{html.escape(r["ready"])}</p>
<p style="margin:0 0 12px;">{html.escape(intro)}</p>
<ul style="margin:0;padding-left:20px;">{lista_html}</ul>
{acceso_html}{nota_html}{informes_html}</div>
<p class="pie">{html.escape(t["footer"])}</p>
</div>
</body>
</html>
"""
    return DossierEmail(subject=f"Dossiers: {titulo}", text=text, html=html_doc, attachments=tuple(adjuntos))


def _pdf_adjunto(dossier: Dossier, lang: str) -> tuple[EmailAttachment, ...]:
    """El PDF del dossier, o nada si no se pudo generar: el correo sale igual con el informe
    completo en el cuerpo."""
    try:
        pdf = render_dossier_pdf(dossier, language=lang)
    except Exception as exc:  # noqa: BLE001 - el PDF es accesorio: nunca impide el correo
        logger.warning("No se pudo generar el PDF del dossier %s: %s", dossier.id, exc)
        return ()
    return (EmailAttachment(dossier_pdf_filename(dossier), pdf, "application/pdf"),)


def resend_wait_seconds(dossier: Dossier, *, now: datetime) -> int:
    """Segundos que faltan para poder reenviar el dossier a mano; 0 si ya se puede."""
    if dossier.email_sent_at is None:
        return 0
    restante = REENVIO_MINIMO_SEGUNDOS - (now - dossier.email_sent_at).total_seconds()
    return max(0, math.ceil(restante))


def send_dossier_email(
    dossier: Dossier, *, recipient: str, language: str | None = None, access_url: str | None = None
) -> None:
    """Envía el dossier completo y lo marca enviado. No hace commit: lo decide quien llama.

    Si el envío falla, el error se propaga y las columnas ``email_*`` quedan como estaban.
    """
    if dossier.status != "complete":
        raise ValueError("Solo se envían dossiers completos.")
    correo = build_dossier_email(
        dossier, language=language, dossier_url=dossier_detail_url(dossier.id), access_url=access_url
    )
    send_email(
        to=[recipient],
        subject=correo.subject,
        text=correo.text,
        html=correo.html,
        attachments=list(correo.attachments),
    )
    marcar_enviado(dossier, recipient)


def _enlaces_de(db: Session) -> Callable[[Dossier], str]:
    """S6.2: crea un enlace de un solo uso por dossier, a nombre de quien lo pidió."""
    return lambda d: url_de_acceso_o_nada(db, d, user_id=d.requested_by_user_id) or dossier_detail_url(d.id)


def marcar_enviado(dossier: Dossier, recipient: str) -> None:
    dossier.email_sent = True
    dossier.email_sent_at = datetime.now(UTC)
    dossier.email_recipients = list(dict.fromkeys([*(dossier.email_recipients or []), recipient]))


def _entregar(
    db: Session,
    dossiers: Sequence[Dossier],
    recipient: str,
    armar: Callable[[], DossierEmail],
    *,
    kind: str,
    calendar_event_id: UUID | None = None,
    meeting_title: str | None = None,
    language: str | None = None,
) -> bool:
    """Envío automático con reintentos (S6.4): hasta 3 intentos seguidos y, si siguen fallando
    por algo pasajero, queda en espera (``dossier_email_retries``). Nunca lanza.

    Cada ronda deja un registro ``EMAIL dossier_auto`` por dossier (S6.6).
    """
    base: dict[str, Any] = {
        "origen": "calendario" if kind == "reunion" else "persona",
        "calendar_event_id": str(calendar_event_id) if calendar_event_id else None,
    }
    try:
        correo = armar()
    except Exception as exc:  # noqa: BLE001 - un dossier sin contenido no se envía ni se reintenta
        resultado = ResultadoIntentos(intentos=1, error=exc)
    else:
        resultado = enviar_con_reintentos(
            lambda: send_email(
                to=[recipient],
                subject=correo.subject,
                text=correo.text,
                html=correo.html,
                attachments=list(correo.attachments),
            )
        )
    datos = {**base, "intentos": resultado.intentos, "reintento_programado": False}

    if resultado.error is None:
        for dossier in dossiers:
            marcar_enviado(dossier, recipient)
            auditar_envio(db, evento_envio(dossier, manual=False, datos=datos))
        db.commit()
        return True

    db.rollback()
    programar = isinstance(resultado.error, EmailDeliveryError) and resultado.error.transitorio
    datos["reintento_programado"] = programar
    logger.warning(
        "No se pudo enviar por correo el dossier %s (%s, %s intento(s)); reintento programado: %s",
        ", ".join(str(d.id) for d in dossiers),
        type(resultado.error).__name__,
        resultado.intentos,
        programar,
    )
    try:
        for dossier in dossiers:
            auditar_envio(db, evento_envio(dossier, manual=False, error=resultado.error, datos=datos))
        if programar:
            encolar_reintento(
                db,
                kind=kind,
                dossiers=dossiers,
                error=resultado.error,
                calendar_event_id=calendar_event_id,
                meeting_title=meeting_title,
                language=language,
            )
        db.commit()
    except Exception:  # el registro del fallo no puede tumbar a quien llama
        logger.exception("No se pudo registrar el fallo de envío")
        db.rollback()
    return False


def deliver_meeting_dossiers(
    db: Session,
    *,
    dossier_ids: Sequence[UUID | str],
    recipient: str,
    meeting_title: str | None,
    language: str | None,
    calendar_event_id: UUID | None,
) -> bool:
    """Envío automático de los dossiers de una reunión en un solo correo (S6.3).

    Solo van los dossiers completos, y solo al ``recipient`` (el dueño del calendario). Nunca
    lanza: un fallo de correo no cambia el evento ni los dossiers. Cada dossier deja su registro
    ``EMAIL dossier_auto`` (S6.6) y un fallo pasajero queda en espera de reintento (S6.4).
    Devuelve si se envió.
    """
    try:
        ids = [UUID(str(i)) for i in dossier_ids]
        encontrados = {
            d.id: d
            for d in db.scalars(select(Dossier).where(Dossier.id.in_(ids), Dossier.status == "complete"))
        } if ids else {}
    except Exception:  # ids inválidos o base no disponible: no hay nada que enviar
        logger.warning("Correo de reunión omitido: no se pudieron leer los dossiers", exc_info=True)
        db.rollback()
        return False
    completos = [encontrados[i] for i in ids if i in encontrados]
    if not completos:
        logger.info("Correo de reunión omitido: ningún dossier completo (evento %s)", calendar_event_id)
        return False
    return _entregar(
        db,
        completos,
        recipient,
        lambda: build_meeting_email(
            completos, meeting_title=meeting_title, language=language, access_for=_enlaces_de(db)
        ),
        kind="reunion",
        calendar_event_id=calendar_event_id,
        meeting_title=meeting_title,
        language=language,
    )


def evento_envio(
    dossier: Dossier,
    *,
    manual: bool,
    user_id: UUID | None = None,
    error: BaseException | None = None,
    datos: dict[str, Any] | None = None,
) -> AuditEvent:
    """Registro de auditoría de un envío (S6.6).

    Nunca lleva el destinatario: de un error guarda solo su clase, porque el texto del servidor
    SMTP puede traer la dirección.
    """
    return AuditEvent(
        action="EMAIL dossier_manual" if manual else "EMAIL dossier_auto",
        resource_type="dossier",
        resource_id=dossier.id,
        user_id=user_id if manual else dossier.requested_by_user_id,
        organization_id=dossier.organization_id,
        success=error is None,
        error_message=type(error).__name__ if error is not None else None,
        request_data=datos,
    )


def auditar_envio(db: Session, evento: AuditEvent, *, commit: bool = False) -> None:
    """Escribe el registro del envío. Nunca lanza: un fallo de auditoría no cambia el envío."""
    try:
        with db.begin_nested():
            record(db, evento)
        if commit:
            db.commit()
    except Exception:  # la auditoría no puede tumbar el envío (criterio de S4.10)
        logger.warning("No se pudo auditar el envío del dossier %s", evento.resource_id, exc_info=True)
        if commit:
            db.rollback()


def deliver_dossier_after_generation(db: Session, *, dossier_id: UUID | str, recipient: str) -> bool:
    """Envío automático al terminar una generación (S6.1). Nunca lanza: un fallo de correo no
    puede cambiar el resultado del job ni del dossier. Devuelve si se envió.

    Cada ronda, exitosa o fallida, queda en ``audit_logs`` (S6.6), y un fallo pasajero queda en
    espera de reintento (S6.4).
    """
    try:
        dossier = db.get(Dossier, UUID(str(dossier_id)))
    except Exception:  # id inválido o base no disponible
        logger.warning("Correo automático omitido: no se pudo leer el dossier %s", dossier_id, exc_info=True)
        db.rollback()
        return False
    if dossier is None:
        logger.warning("Correo automático omitido: dossier %s no encontrado", dossier_id)
        return False

    def _armar() -> DossierEmail:
        if dossier.status != "complete":
            raise ValueError("Solo se envían dossiers completos.")
        acceso = url_de_acceso_o_nada(db, dossier, user_id=dossier.requested_by_user_id)
        return build_dossier_email(
            dossier, language=None, dossier_url=dossier_detail_url(dossier.id), access_url=acceso
        )

    return _entregar(db, [dossier], recipient, _armar, kind="persona")
