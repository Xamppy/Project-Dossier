"""S5.7 · S6.1 · Plantilla del correo del dossier y registro del envío, sin red ni base.

Criterios CA7–CA9 de ``specs/proposals/S6.1-envio-dossier-correo.md`` y la parte de
``send_dossier_email`` que no depende del servidor (CA10 y CA17 en integración).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from dossier.db.models import Dossier
from dossier.services import dossier_email
from dossier.services.dossier_email import (
    build_dossier_email,
    dossier_detail_url,
    send_dossier_email,
)
from dossier.services.email_service import EmailDeliveryError

URL = "https://app.example.com/dashboard/dossiers/abc"

INFORME = """## Resumen ejecutivo

Ana Prueba dirige **Empresa de Prueba SA** desde 2019.

- Hallazgo uno
- Hallazgo dos

| Cargo | Desde |
|---|---|
| Directora | 2019 |

Fuente: [registro](https://registro.example.com/ana)
"""


def _dossier(body: str | None = INFORME, **extra) -> Dossier:
    data = {"format": "markdown", "body": body, "output_language": "es"}
    data.update(extra.pop("data", {}))
    return Dossier(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        requested_by_user_id=uuid.uuid4(),
        subject_name=extra.pop("subject_name", "Ana Prueba"),
        status=extra.pop("status", "complete"),
        dossier_data=data,
        email_sent=False,
        email_recipients=[],
        **extra,
    )


# --- CA7: contenido completo ---


def test_html_y_texto_llevan_el_informe_completo():
    correo = build_dossier_email(_dossier(), language=None, dossier_url=URL)

    assert correo.subject == "Dossier: Ana Prueba"
    assert "<h2>Resumen ejecutivo</h2>" in correo.html
    assert "<strong>Empresa de Prueba SA</strong>" in correo.html
    assert "<li>Hallazgo dos</li>" in correo.html
    assert "<td>Directora</td>" in correo.html
    assert 'href="https://registro.example.com/ana"' in correo.html
    assert f'href="{URL}"' in correo.html
    assert INFORME.strip() in correo.text
    assert URL in correo.text


def test_html_es_un_documento_completo_con_estilos_en_linea_de_tabla():
    html = build_dossier_email(_dossier(), language=None, dossier_url=URL).html

    assert html.lstrip().lower().startswith("<!doctype html>")
    assert '<html lang="es">' in html
    assert "</html>" in html.rstrip()[-10:]


def test_nombre_con_html_se_limpia_en_asunto_y_se_escapa_en_cuerpo():
    correo = build_dossier_email(
        _dossier(subject_name='<b>Ana</b> "Prueba" & Cía'), language=None, dossier_url=URL
    )

    assert correo.subject == 'Dossier: Ana "Prueba" & Cía'
    assert "<b>Ana</b>" not in correo.html
    assert "&amp; Cía" in correo.html


def test_sin_nombre_usa_un_texto_por_omision():
    correo = build_dossier_email(_dossier(subject_name=None), language="en", dossier_url=URL)

    assert correo.subject == "Dossier: Untitled"


@pytest.mark.parametrize("body", [None, "", "   \n"])
def test_sin_cuerpo_no_se_arma_correo(body):
    with pytest.raises(ValueError):
        build_dossier_email(_dossier(body=body), language=None, dossier_url=URL)


def test_dossier_data_que_no_es_dict_no_se_arma():
    d = _dossier()
    d.dossier_data = ["no", "es", "dict"]

    with pytest.raises(ValueError):
        build_dossier_email(d, language=None, dossier_url=URL)


# --- CA8: nada activo desde el contenido ---


def test_html_crudo_y_enlaces_peligrosos_no_quedan_activos():
    hostil = (
        "<script>alert(1)</script>\n\n"
        '<img src=x onerror="alert(2)">\n\n'
        "[clic](javascript:alert(3)) [dato](data:text/html;base64,PHNjcmlwdD4=) "
        "[vb](vbscript:msgbox(1))"
    )
    html = build_dossier_email(_dossier(body=hostil), language=None, dossier_url=URL).html

    assert "<script" not in html.lower()
    assert "<img" not in html.lower()
    assert 'href="javascript:' not in html.lower()
    assert 'href="data:' not in html.lower()
    assert 'href="vbscript:' not in html.lower()
    assert "&lt;script&gt;" in html


def test_url_del_dossier_se_escapa_en_el_atributo():
    html = build_dossier_email(
        _dossier(), language=None, dossier_url='https://e.com/"><script>x</script>'
    ).html

    assert '"><script>' not in html


# --- CA9: idioma ---


@pytest.mark.parametrize(
    ("codigo", "boton"),
    [
        ("es", "Abrir en Project Dossier"),
        ("en", "Open in Project Dossier"),
        ("en-GB", "Open in Project Dossier"),
        ("pt", "Abrir no Project Dossier"),
        ("it", "Apri in Project Dossier"),
        ("fr", "Ouvrir dans Project Dossier"),
        ("de", "In Project Dossier öffnen"),
    ],
)
def test_textos_fijos_en_el_idioma_pedido(codigo, boton):
    correo = build_dossier_email(_dossier(), language=codigo, dossier_url=URL)

    assert boton in correo.html
    assert boton in correo.text


def test_sin_idioma_explicito_usa_el_del_dossier():
    d = _dossier(data={"output_language": "fr"})

    assert "Ouvrir dans Project Dossier" in build_dossier_email(d, language=None, dossier_url=URL).html


def test_idioma_desconocido_cae_a_espanol():
    d = _dossier(data={"output_language": "xx"})

    assert "Abrir en Project Dossier" in build_dossier_email(d, language=None, dossier_url=URL).html


# --- Enlace al dossier ---


def test_url_del_detalle_usa_dossier_frontend_url_o_frontend_url(monkeypatch):
    dossier_id = uuid.uuid4()
    monkeypatch.delenv("DOSSIER_FRONTEND_URL", raising=False)
    monkeypatch.setenv("FRONTEND_URL", "https://front.example.com/")
    assert dossier_detail_url(dossier_id) == f"https://front.example.com/dashboard/dossiers/{dossier_id}"

    monkeypatch.setenv("DOSSIER_FRONTEND_URL", "https://dossier.example.com")
    assert dossier_detail_url(dossier_id).startswith("https://dossier.example.com/dashboard/")


# --- Registro del envío ---


@pytest.fixture
def enviados(monkeypatch):
    lista: list[dict] = []
    monkeypatch.setattr(dossier_email, "send_email", lambda **kw: lista.append(kw))
    return lista


def test_envio_correcto_marca_el_dossier(enviados):
    d = _dossier()
    antes = datetime.now(UTC)

    send_dossier_email(d, recipient="ana@example.com")

    assert enviados[0]["to"] == ["ana@example.com"]
    assert enviados[0]["subject"] == "Dossier: Ana Prueba"
    assert d.email_sent is True
    assert d.email_sent_at is not None and d.email_sent_at >= antes
    assert d.email_recipients == ["ana@example.com"]


def test_reenvio_no_duplica_destinatarios(enviados):
    d = _dossier()
    d.email_recipients = ["ana@example.com"]

    send_dossier_email(d, recipient="ana@example.com")
    send_dossier_email(d, recipient="beto@example.com")

    assert d.email_recipients == ["ana@example.com", "beto@example.com"]


def test_fallo_del_envio_no_toca_el_dossier(monkeypatch):
    def falla(**_):
        raise EmailDeliveryError("caído")

    monkeypatch.setattr(dossier_email, "send_email", falla)
    d = _dossier()

    with pytest.raises(EmailDeliveryError):
        send_dossier_email(d, recipient="ana@example.com")
    assert d.email_sent is False
    assert d.email_sent_at is None
    assert d.email_recipients == []


@pytest.mark.parametrize("estado", ["failed", "pending"])
def test_dossier_no_completo_no_se_envia(enviados, estado):
    with pytest.raises(ValueError):
        send_dossier_email(_dossier(status=estado), recipient="ana@example.com")
    assert enviados == []


# --- Enfriamiento del envío manual (CA16) ---


def test_sin_envio_previo_no_hay_espera():
    assert dossier_email.resend_wait_seconds(_dossier(), now=datetime.now(UTC)) == 0


def test_envio_reciente_pide_esperar_lo_que_falta():
    ahora = datetime(2026, 11, 2, 12, 0, 30, tzinfo=UTC)
    d = _dossier()
    d.email_sent_at = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)

    assert dossier_email.resend_wait_seconds(d, now=ahora) == 30


def test_pasado_el_minuto_ya_no_hay_espera():
    ahora = datetime(2026, 11, 2, 12, 1, 0, tzinfo=UTC)
    d = _dossier()
    d.email_sent_at = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)

    assert dossier_email.resend_wait_seconds(d, now=ahora) == 0


def test_fraccion_de_segundo_redondea_hacia_arriba():
    d = _dossier()
    d.email_sent_at = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)

    assert dossier_email.resend_wait_seconds(d, now=datetime(2026, 11, 2, 12, 0, 59, 500_000, tzinfo=UTC)) == 1
