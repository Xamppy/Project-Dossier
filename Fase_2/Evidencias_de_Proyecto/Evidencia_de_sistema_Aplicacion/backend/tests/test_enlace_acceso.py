"""S6.2, unitarias: token, URL con fragmento y textos del correo (CA5, CA6, CA7).

Especificación: ``specs/proposals/S6.2-enlace-un-solo-uso.md``.
"""
from __future__ import annotations

import re
import uuid

import pytest

from dossier.db.models import Dossier
from dossier.services.dossier_access_links import (
    hash_token,
    nuevo_token,
    url_de_acceso,
    url_de_acceso_o_nada,
)
from dossier.services.dossier_email import build_dossier_email, build_meeting_email


def test_el_token_es_largo_y_distinto_cada_vez():
    a, b = nuevo_token(), nuevo_token()
    assert a != b
    assert len(a) >= 43  # 32 bytes en base64 url-safe


def test_solo_se_guarda_el_hash():
    token = nuevo_token()
    h = hash_token(token)
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert token not in h
    assert hash_token(token) == h


def test_el_token_va_en_el_fragmento(monkeypatch):
    monkeypatch.setenv("DOSSIER_FRONTEND_URL", "https://app.example.test/")
    url = url_de_acceso("abc123")
    assert url == "https://app.example.test/acceso#t=abc123"
    assert "?" not in url


def test_si_no_se_puede_crear_el_enlace_el_correo_usa_el_dashboard():
    class _SinBase:
        def begin_nested(self):
            raise RuntimeError("base caída")

    assert url_de_acceso_o_nada(_SinBase(), _dossier(), user_id=uuid.uuid4()) is None


def _dossier(nombre="Ana Prueba", lang="es") -> Dossier:
    return Dossier(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), requested_by_user_id=uuid.uuid4(),
        subject_name=nombre, status="complete",
        dossier_data={"format": "markdown", "body": "## Resumen\n\nInforme.", "output_language": lang},
    )


ACCESO = "https://app.test/acceso#t=TOKEN-UNO"
PANEL = "https://app.test/dashboard/dossiers/xyz"


def test_el_correo_lleva_el_enlace_el_dashboard_y_la_nota():
    correo = build_dossier_email(_dossier(), language="es", dossier_url=PANEL, access_url=ACCESO)
    assert f'href="{ACCESO}"' in correo.html.replace("&amp;", "&")
    assert PANEL in correo.html
    assert "sirve una vez" in correo.text
    assert "24 horas" in correo.text
    assert ACCESO in correo.text and PANEL in correo.text


def test_sin_enlace_el_correo_queda_como_antes():
    correo = build_dossier_email(_dossier(), language="es", dossier_url=PANEL)
    assert "sirve una vez" not in correo.text
    assert f'href="{PANEL}"' in correo.html


@pytest.mark.parametrize("idioma, palabra", [("es", "24"), ("en", "24"), ("pt", "24"), ("it", "24"),
                                              ("fr", "24"), ("de", "24")])
def test_la_nota_esta_en_cada_idioma(idioma, palabra):
    correo = build_dossier_email(_dossier(lang=idioma), language=idioma, dossier_url=PANEL, access_url=ACCESO)
    assert palabra in correo.text
    assert ACCESO in correo.text


def test_el_correo_de_reunion_usa_un_enlace_por_dossier():
    dossiers = [_dossier("Acme SA"), _dossier("Ana Prueba")]
    enlaces = {d.id: f"https://app.test/acceso#t=T-{i}" for i, d in enumerate(dossiers)}
    correo = build_meeting_email(dossiers, meeting_title="Demo", language="es",
                                 url_for=lambda i: PANEL, access_for=lambda d: enlaces[d.id])
    for url in enlaces.values():
        assert url in correo.html
        assert url in correo.text
    assert "sirve una vez" in correo.text
