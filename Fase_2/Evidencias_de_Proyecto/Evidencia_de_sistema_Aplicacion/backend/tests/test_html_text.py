"""BUG-2026-10-19-10: el saneador HTML borraba un `<correo>` escrito tal cual.

`strip_html_to_text` trataba `<ana@acme.test>` como una etiqueta y lo eliminaba; solo sobrevivía
escapado (`&lt;…&gt;`). El lector de participantes del calendario usa justo el formato
«Nombre <correo>» (BUG-2026-10-19-05), así que los ángulos se conservan.
"""
from __future__ import annotations

import pytest

from dossier.utils.html_text import strip_html_to_plain_line, strip_html_to_text


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("Contacto: Ana Pérez <ana@acme.test>", "Contacto: Ana Pérez <ana@acme.test>"),
        ("<ana.perez+ventas@acme-corp.co.uk>", "<ana.perez+ventas@acme-corp.co.uk>"),
        ("Contacto: Ana Pérez < ana@acme.test >", "Contacto: Ana Pérez <ana@acme.test>"),
        ("<p>Contacto: Ana <ana@acme.test></p>", "Contacto: Ana <ana@acme.test>"),
    ],
)
def test_un_correo_entre_angulos_se_conserva(entrada, esperado):
    assert strip_html_to_text(entrada) == esperado


def test_el_correo_escapado_sigue_igual():
    assert strip_html_to_text("Ana &lt;ana@acme.test&gt;") == "Ana <ana@acme.test>"


def test_las_etiquetas_reales_se_siguen_quitando():
    assert strip_html_to_text('<b>Hola</b> <script>alert(1)</script><a href="mailto:a@b.co">a@b.co</a>') == (
        "Hola alert(1) a@b.co"
    )


def test_los_saltos_de_linea_se_conservan():
    assert strip_html_to_text("Línea 1<br>Línea 2<p>Línea 3</p>") == "Línea 1\nLínea 2 Línea 3"


def test_una_etiqueta_con_arroba_en_un_atributo_no_es_un_correo():
    assert strip_html_to_text('<img alt="x@y.z" src="a.png">Texto') == "Texto"


def test_la_version_de_una_linea_tambien_conserva_el_correo():
    assert strip_html_to_plain_line("Reunión con Ana <ana@acme.test>") == "Reunión con Ana <ana@acme.test>"
