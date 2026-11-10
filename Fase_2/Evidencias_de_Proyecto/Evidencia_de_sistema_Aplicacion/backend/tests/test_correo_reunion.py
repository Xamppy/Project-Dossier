"""S6.3, unitarias: el correo único con los dossiers de una reunión (CA2, CA9).

Especificación: ``specs/proposals/S6.3-calendario-correo.md``.
"""
from __future__ import annotations

import uuid

import pytest

from dossier.db.models import Dossier
from dossier.services import dossier_email
from dossier.services.dossier_email import build_meeting_email


def _dossier(nombre: str, cuerpo: str = "## Resumen\n\nInforme de prueba.") -> Dossier:
    return Dossier(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        requested_by_user_id=uuid.uuid4(),
        subject_name=nombre,
        status="complete",
        dossier_data={"format": "markdown", "body": cuerpo, "output_language": "es"},
    )


def _url(dossier_id) -> str:
    return f"https://app.test/dashboard/dossiers/{dossier_id}"


def test_un_correo_con_un_pdf_por_dossier():
    dossiers = [_dossier("Acme SA"), _dossier("Ana Prueba"), _dossier("Luis Prueba")]
    correo = build_meeting_email(dossiers, meeting_title="Reunión comercial Acme", language="es",
                                 url_for=_url)
    assert correo.subject == "Dossiers: Reunión comercial Acme"
    assert len(correo.attachments) == 3
    assert {a.mime_type for a in correo.attachments} == {"application/pdf"}
    for d in dossiers:
        assert d.subject_name in correo.text
        assert _url(d.id) in correo.html


@pytest.mark.parametrize(
    "idioma, sin_titulo",
    [("es", "tu reunión"), ("en", "your meeting"), ("pt", "a sua reunião"), ("it", "la tua riunione"),
     ("fr", "votre réunion"), ("de", "Ihr Meeting")],
)
def test_sin_titulo_usa_tu_reunion_en_el_idioma(idioma, sin_titulo):
    correo = build_meeting_email([_dossier("Acme SA")], meeting_title=None, language=idioma, url_for=_url)
    assert correo.subject == f"Dossiers: {sin_titulo}"


def test_el_titulo_y_los_nombres_se_escapan_en_el_html():
    correo = build_meeting_email(
        [_dossier("<img src=x onerror=alert(1)>")],
        meeting_title="<script>alert('x')</script> Demo",
        language="es",
        url_for=_url,
    )
    assert "<script>" not in correo.html
    assert "<img src=x" not in correo.html


def test_si_un_pdf_falla_su_informe_va_en_el_cuerpo(monkeypatch):
    ok, roto = _dossier("Acme SA"), _dossier("Ana Prueba", cuerpo="Texto único del informe de Ana.")
    real = dossier_email.render_dossier_pdf

    def _render(dossier, language):
        if dossier is roto:
            raise RuntimeError("ReportLab falló")
        return real(dossier, language=language)

    monkeypatch.setattr(dossier_email, "render_dossier_pdf", _render)
    correo = build_meeting_email([ok, roto], meeting_title="Demo", language="es", url_for=_url)

    assert len(correo.attachments) == 1
    assert "Texto único del informe de Ana." in correo.text


def test_sin_dossiers_no_hay_correo():
    with pytest.raises(ValueError):
        build_meeting_email([], meeting_title="Demo", language="es", url_for=_url)
