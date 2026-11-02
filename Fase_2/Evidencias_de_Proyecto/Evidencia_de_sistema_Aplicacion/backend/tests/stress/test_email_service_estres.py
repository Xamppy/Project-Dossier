"""S5.6 · El servicio SMTP con volumen, concurrencia y un servidor que no responde."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from dossier.services.email_service import EmailDeliveryError, send_email


def test_servidor_mudo_corta_por_tiempo_limite(servidor_smtp, monkeypatch):
    servidor_smtp.mudo = True
    monkeypatch.setenv("SMTP_TIMEOUT_SECONDS", "0.5")

    inicio = time.monotonic()
    with pytest.raises(EmailDeliveryError):
        send_email(to=["ana@example.com"], subject="x", text="x", html="<p>x</p>")
    assert time.monotonic() - inicio < 2.5


def test_cuerpo_de_500_kb_llega_completo(servidor_smtp):
    parrafo = "Hallazgo relevante sobre la trayectoria profesional. " * 20
    html = "".join(f"<p>{i} {parrafo}</p>" for i in range(500))
    assert len(html) > 500_000

    send_email(to=["ana@example.com"], subject="Grande", text=html, html=html)

    recibido = servidor_smtp.mensajes[0].get_body(("html",)).get_content()
    assert "<p>499 " in recibido
    assert len(recibido) >= len(html)


def test_veinte_envios_simultaneos_llegan_todos(servidor_smtp):
    def enviar(i: int) -> None:
        send_email(to=[f"u{i}@example.com"], subject=f"Dossier {i}", text="x", html="<p>x</p>")

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(enviar, range(20)))

    asuntos = sorted(m["Subject"] for m in servidor_smtp.mensajes)
    assert asuntos == sorted(f"Dossier {i}" for i in range(20))
