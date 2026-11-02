"""
Correo del dossier (S5.7) y su envío con registro en ``dossiers`` (S6.1).

El correo lleva el informe **completo** (``dossier_data.body``) convertido de Markdown a HTML,
más una versión en texto plano. El HTML crudo del informe se escapa: viene del LLM y de fuentes
externas, y en un correo no hay CSP que lo contenga.
"""
from __future__ import annotations

import html
import logging
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from markdown_it import MarkdownIt
from sqlalchemy.orm import Session

from dossier.db.models import Dossier
from dossier.services.email_service import send_email
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
        "footer": (
            "Este correo contiene información confidencial sobre una persona. "
            "No lo reenvíes fuera de tu organización."
        ),
    },
    "en": {
        "untitled": "Untitled",
        "ready": "Your dossier is ready",
        "intro": "This is the complete dossier on {name} generated in Project Dossier.",
        "open": "Open in Project Dossier",
        "footer": (
            "This email contains confidential information about a person. "
            "Do not forward it outside your organization."
        ),
    },
    "pt": {
        "untitled": "Sem nome",
        "ready": "O seu dossiê está pronto",
        "intro": "Este é o dossiê completo de {name} gerado no Project Dossier.",
        "open": "Abrir no Project Dossier",
        "footer": (
            "Este e-mail contém informação confidencial sobre uma pessoa. "
            "Não o reencaminhe para fora da sua organização."
        ),
    },
    "it": {
        "untitled": "Senza nome",
        "ready": "Il tuo dossier è pronto",
        "intro": "Questo è il dossier completo su {name} generato in Project Dossier.",
        "open": "Apri in Project Dossier",
        "footer": (
            "Questa email contiene informazioni riservate su una persona. "
            "Non inoltrarla al di fuori della tua organizzazione."
        ),
    },
    "fr": {
        "untitled": "Sans nom",
        "ready": "Votre dossier est prêt",
        "intro": "Voici le dossier complet sur {name} généré dans Project Dossier.",
        "open": "Ouvrir dans Project Dossier",
        "footer": (
            "Cet e-mail contient des informations confidentielles sur une personne. "
            "Ne le transférez pas en dehors de votre organisation."
        ),
    },
    "de": {
        "untitled": "Ohne Namen",
        "ready": "Ihr Dossier ist fertig",
        "intro": "Dies ist das vollständige Dossier zu {name}, erstellt in Project Dossier.",
        "open": "In Project Dossier öffnen",
        "footer": (
            "Diese E-Mail enthält vertrauliche Informationen über eine Person. "
            "Leiten Sie sie nicht außerhalb Ihrer Organisation weiter."
        ),
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


def build_dossier_email(dossier: Dossier, *, language: str | None, dossier_url: str) -> DossierEmail:
    body = _cuerpo(dossier)
    lang = _idioma(dossier, language)
    t = _TEXTOS[lang]
    nombre = strip_html_to_plain_line(dossier.subject_name, max_len=255) or t["untitled"]
    intro = t["intro"].format(name=nombre)

    text = "\n\n".join(
        [t["ready"], intro, f"{t['open']}: {dossier_url}", "-" * 40, body, "-" * 40, t["footer"]]
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
<p style="margin:0 0 24px;"><a class="boton" href="{html.escape(dossier_url, quote=True)}">{html.escape(t["open"])}</a></p>
<hr style="border:none;border-top:1px solid #e5e7eb;margin:0 0 16px;">
<div class="informe">
{_MARKDOWN.render(body)}
</div>
</div>
<p class="pie">{html.escape(t["footer"])}</p>
</div>
</body>
</html>
"""
    return DossierEmail(subject=f"Dossier: {nombre}", text=text, html=html_doc)


def resend_wait_seconds(dossier: Dossier, *, now: datetime) -> int:
    """Segundos que faltan para poder reenviar el dossier a mano; 0 si ya se puede."""
    if dossier.email_sent_at is None:
        return 0
    restante = REENVIO_MINIMO_SEGUNDOS - (now - dossier.email_sent_at).total_seconds()
    return max(0, math.ceil(restante))


def send_dossier_email(dossier: Dossier, *, recipient: str, language: str | None = None) -> None:
    """Envía el dossier completo y lo marca enviado. No hace commit: lo decide quien llama.

    Si el envío falla, el error se propaga y las columnas ``email_*`` quedan como estaban.
    """
    if dossier.status != "complete":
        raise ValueError("Solo se envían dossiers completos.")
    correo = build_dossier_email(dossier, language=language, dossier_url=dossier_detail_url(dossier.id))
    send_email(to=[recipient], subject=correo.subject, text=correo.text, html=correo.html)
    dossier.email_sent = True
    dossier.email_sent_at = datetime.now(UTC)
    dossier.email_recipients = list(dict.fromkeys([*(dossier.email_recipients or []), recipient]))


def deliver_dossier_after_generation(db: Session, *, dossier_id: UUID | str, recipient: str) -> bool:
    """Envío automático al terminar una generación (S6.1). Nunca lanza: un fallo de correo no
    puede cambiar el resultado del job ni del dossier. Devuelve si se envió.
    """
    try:
        dossier = db.get(Dossier, UUID(str(dossier_id)))
        if dossier is None:
            logger.warning("Correo automático omitido: dossier %s no encontrado", dossier_id)
            return False
        send_dossier_email(dossier, recipient=recipient)
        db.commit()
        return True
    except Exception as exc:  # noqa: BLE001 - el correo es accesorio: ningún fallo sube al job
        db.rollback()
        logger.warning("No se pudo enviar por correo el dossier %s: %s", dossier_id, exc)
        return False
