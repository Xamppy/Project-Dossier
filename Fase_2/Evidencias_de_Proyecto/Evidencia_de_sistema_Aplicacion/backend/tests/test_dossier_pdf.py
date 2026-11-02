"""S6.1 · PDF del dossier adjunto al correo, con el formato del detalle web (CA21–CA25).

El PDF se lee de vuelta con ``pypdf``: se comprueba lo que un lector vería, no cómo se dibujó.
"""
from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime

import pytest
from pypdf import PdfReader

from dossier.db.models import Dossier
from dossier.services.dossier_pdf import dossier_pdf_filename, render_dossier_pdf

INFORME = """## Resumen ejecutivo

Ana Prueba dirige **Empresa de Prueba SA** desde 2019 y tiene *perfil* ~~antiguo~~ `técnico`.

- Hallazgo uno
- Hallazgo dos
  - Detalle anidado

1. Primer paso
2. Segundo paso

| Cargo | Empresa | Desde |
|---|---|---|
| Directora | Empresa de Prueba SA | 2019 |

> Cita del informe.

```
bloque de código
```

---

Fuente: [registro](https://registro.example.com/ana)
"""


def _dossier(body: str | None = INFORME, **extra) -> Dossier:
    data = {"format": "markdown", "body": body, "output_language": "es", "pipeline": "person_research"}
    data.update(extra.pop("data", {}))
    return Dossier(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        requested_by_user_id=uuid.uuid4(),
        subject_name=extra.pop("subject_name", "Ana Prueba"),
        subject_email=extra.pop("subject_email", "ana@empresa.example.com"),
        status="complete",
        dossier_data=data,
        alerts=extra.pop("alerts", []),
        created_at=extra.pop("created_at", datetime(2026, 11, 2, 12, 0, tzinfo=UTC)),
        updated_at=extra.pop("updated_at", datetime(2026, 11, 2, 12, 5, tzinfo=UTC)),
        **extra,
    )


def _leer(pdf: bytes) -> tuple[PdfReader, str]:
    lector = PdfReader(io.BytesIO(pdf))
    texto = "\n".join(p.extract_text() for p in lector.pages)
    return lector, " ".join(texto.split())


def _enlaces(lector: PdfReader) -> list[str]:
    uris = []
    for pagina in lector.pages:
        for anotacion in pagina.get("/Annots") or []:
            accion = anotacion.get_object().get("/A") or {}
            if "/URI" in accion:
                uris.append(str(accion["/URI"]))
    return uris


# --- CA21: un PDF válido con el formato del detalle web ---


def test_es_un_pdf_con_titulo_y_autor():
    pdf = render_dossier_pdf(_dossier())

    assert pdf.startswith(b"%PDF-")
    lector, _ = _leer(pdf)
    assert lector.metadata.title == "Dossier: Ana Prueba"
    assert lector.metadata.author == "TraceLens"


def test_encabezado_como_en_la_web():
    _, texto = _leer(render_dossier_pdf(_dossier()))

    for esperado in (
        "COMPLETO",
        "INFORME EN ESPAÑOL",
        "Ana Prueba",
        "ana@empresa.example.com",
        "Creado 2 de noviembre de 2026 · Actualizado 2 de noviembre de 2026",
        "Informe generado por IA",
    ):
        assert esperado in texto, esperado


def test_lleva_el_logo_de_tracelens():
    lector, _ = _leer(render_dossier_pdf(_dossier()))

    recursos = lector.pages[0]["/Resources"]
    imagenes = [o for o in (recursos.get("/XObject") or {}).values() if o.get_object()["/Subtype"] == "/Image"]
    assert imagenes


# --- CA22: el informe completo ---


def test_contiene_el_informe_completo():
    _, texto = _leer(render_dossier_pdf(_dossier()))

    for esperado in (
        "Resumen ejecutivo",
        "Ana Prueba dirige Empresa de Prueba SA desde 2019",
        "Hallazgo dos",
        "Detalle anidado",
        "Segundo paso",
        "Cargo",
        "Directora",
        "Cita del informe.",
        "bloque de código",
        "registro",
    ):
        assert esperado in texto, esperado


def test_alertas_de_riesgo_al_final():
    _, texto = _leer(render_dossier_pdf(_dossier(alerts=["Litigio abierto en 2024", {"nivel": "alto"}])))

    assert "Alertas de riesgo" in texto
    assert "Litigio abierto en 2024" in texto
    assert "alto" in texto


def test_pie_con_paginacion_en_cada_pagina():
    largo = "\n\n".join(f"## Sección {i}\n\n" + "Texto del hallazgo. " * 60 for i in range(30))
    lector, _ = _leer(render_dossier_pdf(_dossier(body=largo)))

    total = len(lector.pages)
    assert total > 1
    for n, pagina in enumerate(lector.pages, start=1):
        assert f"Página {n} de {total}" in pagina.extract_text()


# --- CA23: nada activo ni roto por el contenido ---


def test_html_y_marcado_de_reportlab_se_muestran_como_texto():
    hostil = '<script>alert(1)</script> <b>no negrita</b> <font color="red">x</font> & <para>'

    _, texto = _leer(render_dossier_pdf(_dossier(body=hostil)))

    assert "<script>alert(1)</script>" in texto
    assert "<b>no negrita</b>" in texto
    assert "& <para>" in texto


def test_solo_enlaces_http_https_y_mailto_son_clicables():
    body = (
        "[web](https://registro.example.com/ana) [correo](mailto:ana@example.com) "
        "[js](javascript:alert(1)) [archivo](file:///etc/passwd) [rel](/dashboard)"
    )

    lector, texto = _leer(render_dossier_pdf(_dossier(body=body)))

    assert sorted(_enlaces(lector)) == ["https://registro.example.com/ana", "mailto:ana@example.com"]
    assert "archivo" in texto and "rel" in texto


def test_caracteres_fuera_de_latin_no_rompen_el_pdf():
    _, texto = _leer(render_dossier_pdf(_dossier(subject_name="李 Ana 🚀", body="Emoji 🚀 y flecha → listo")))

    assert "Ana" in texto
    assert "listo" in texto


@pytest.mark.parametrize("body", [None, "", "  \n"])
def test_sin_cuerpo_no_hay_pdf(body):
    with pytest.raises(ValueError):
        render_dossier_pdf(_dossier(body=body))


# --- CA24: idioma ---


@pytest.mark.parametrize(
    ("codigo", "esperados"),
    [
        ("en", ["COMPLETE", "REPORT IN ENGLISH", "AI-generated report", "Created November 2, 2026", "Page 1 of 1"]),
        ("pt", ["COMPLETO", "RELATÓRIO EM PORTUGUÊS", "Relatório gerado por IA", "Página 1 de 1"]),
        ("it", ["COMPLETATO", "REPORT IN ITALIANO", "Report generato da IA", "Pagina 1 di 1"]),
        ("fr", ["COMPLET", "RAPPORT EN FRANÇAIS", "Rapport généré par IA", "Page 1 sur 1"]),
        ("de", ["ABGESCHLOSSEN", "BERICHT AUF DEUTSCH", "KI-generierter Bericht", "Seite 1 von 1"]),
    ],
)
def test_textos_fijos_en_el_idioma_del_dossier(codigo, esperados):
    _, texto = _leer(render_dossier_pdf(_dossier(body="Breve.", data={"output_language": codigo})))

    for esperado in esperados:
        assert esperado in texto, esperado


# --- CA25: nombre del archivo ---


@pytest.mark.parametrize(
    ("nombre", "archivo"),
    [
        ("Ana Prueba Ficticia", "dossier-ana-prueba-ficticia.pdf"),
        ("José Ñúñez-Pérez", "dossier-jose-nunez-perez.pdf"),
        ("../../etc/passwd", "dossier-etc-passwd.pdf"),
        ("<b>Ana</b>", "dossier-ana.pdf"),
        ("", "dossier.pdf"),
        (None, "dossier.pdf"),
        ("李", "dossier.pdf"),
    ],
)
def test_nombre_de_archivo_seguro(nombre, archivo):
    assert dossier_pdf_filename(_dossier(subject_name=nombre)) == archivo


def test_nombre_de_archivo_largo_se_corta():
    archivo = dossier_pdf_filename(_dossier(subject_name="Nombre " * 40))

    assert archivo.startswith("dossier-nombre-nombre")
    assert len(archivo) <= 72
    assert archivo.endswith(".pdf") and "-.pdf" not in archivo
