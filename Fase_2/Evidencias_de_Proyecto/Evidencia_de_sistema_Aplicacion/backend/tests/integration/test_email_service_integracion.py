"""S5.6 · ``send_email`` contra un servidor SMTP real en loopback (fixture ``servidor_smtp``).

Cubre lo que el doble de ``smtplib`` no puede: que el mensaje viaje por el protocolo y llegue
entero, con sobre, cabeceras y las dos alternativas legibles.
"""
from __future__ import annotations

import pytest

from dossier.services.email_service import EmailAttachment, EmailDeliveryError, send_email


def test_el_mensaje_llega_entero_al_servidor(servidor_smtp):
    send_email(
        to=["ana@example.com"],
        subject="Dossier: Ana Prueba",
        text="Informe completo en texto.\n\n.línea que empieza con punto",
        html="<h1>Informe</h1><p>Contenido completo con acentos: áéíóú ñ</p>",
    )

    (msg,) = servidor_smtp.mensajes
    assert servidor_smtp.sobres[0] == {"from": "dossier@example.com", "to": ["ana@example.com"]}
    assert msg["Subject"] == "Dossier: Ana Prueba"
    assert msg["Message-ID"]
    texto = msg.get_body(("plain",)).get_content()
    html = msg.get_body(("html",)).get_content()
    assert ".línea que empieza con punto" in texto
    assert "áéíóú ñ" in html


def test_destinatario_rechazado_por_el_servidor(servidor_smtp):
    servidor_smtp.rechazar = True

    with pytest.raises(EmailDeliveryError, match="SMTPRecipientsRefused"):
        send_email(to=["nadie@example.com"], subject="x", text="x", html="<p>x</p>")
    assert servidor_smtp.mensajes == []


def test_el_pdf_adjunto_llega_intacto(servidor_smtp):
    pdf = b"%PDF-1.4\n" + bytes(range(256)) * 400 + b"\n%%EOF"

    send_email(
        to=["ana@example.com"],
        subject="Dossier: Ana",
        text="Texto",
        html="<p>HTML</p>",
        attachments=[EmailAttachment("dossier-ana.pdf", pdf, "application/pdf")],
    )

    (adjunto,) = list(servidor_smtp.mensajes[0].iter_attachments())
    assert adjunto.get_filename() == "dossier-ana.pdf"
    assert adjunto.get_content() == pdf
