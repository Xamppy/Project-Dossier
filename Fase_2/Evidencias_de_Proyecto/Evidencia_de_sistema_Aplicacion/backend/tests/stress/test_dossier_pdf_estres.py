"""S6.1 · Estrés del PDF del dossier: informe enorme, celdas que no caben y muchos a la vez."""
from __future__ import annotations

import io
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from pypdf import PdfReader

from dossier.db.models import Dossier
from dossier.services.dossier_pdf import render_dossier_pdf


def _dossier(body: str) -> Dossier:
    return Dossier(id=uuid.uuid4(), subject_name="Ana", status="complete",
                   dossier_data={"body": body, "output_language": "es"}, alerts=[])


def test_informe_de_500_kb_genera_un_pdf_completo_en_tiempo_razonable():
    body = "\n\n".join(
        f"## Sección {i}\n\n" + "Hallazgo sobre la trayectoria profesional. " * 25
        + f"\n\n- punto {i}\n\n| a | b |\n|---|---|\n| {i} | x |"
        for i in range(450)
    )
    assert len(body) > 500_000

    inicio = time.monotonic()
    pdf = render_dossier_pdf(_dossier(body))
    assert time.monotonic() - inicio < 30

    lector = PdfReader(io.BytesIO(pdf))
    assert "Sección 449" in " ".join(p.extract_text() for p in lector.pages[-3:])
    assert len(pdf) < 5_000_000, "muy por debajo del límite de 25 MB de Gmail"


def test_celda_que_no_cabe_en_una_pagina_no_rompe_el_pdf():
    enorme = "texto de la celda " * 2000
    body = f"| Campo | Valor |\n|---|---|\n| Resumen | {enorme} |\n| Cargo | Directora |"

    lector = PdfReader(io.BytesIO(render_dossier_pdf(_dossier(body))))

    texto = " ".join(p.extract_text() for p in lector.pages)
    assert "Resumen" in texto and "Directora" in texto
    assert len(lector.pages) > 1


def test_fila_de_columnas_angostas_y_largas_no_rompe_el_pdf():
    cabecera = "| " + " | ".join(f"C{i}" for i in range(6)) + " |\n|" + "---|" * 6
    fila = "| " + " | ".join("palabra " * 130 for _ in range(6)) + " |"

    lector = PdfReader(io.BytesIO(render_dossier_pdf(_dossier(f"{cabecera}\n{fila}"))))

    assert "C5" in " ".join(p.extract_text() for p in lector.pages)


def test_lista_y_cita_muy_largas_se_reparten_en_paginas():
    body = "\n".join(f"- elemento {i} " + "detalle " * 30 for i in range(400))
    body += "\n\n" + "\n".join(f"> línea citada {i} " + "texto " * 30 for i in range(200))

    lector = PdfReader(io.BytesIO(render_dossier_pdf(_dossier(body))))

    texto = " ".join(p.extract_text() for p in lector.pages)
    assert "elemento 399" in texto and "línea citada 199" in " ".join(texto.split())


def test_diez_pdf_a_la_vez_salen_todos_validos():
    with ThreadPoolExecutor(max_workers=10) as pool:
        pdfs = list(pool.map(lambda i: render_dossier_pdf(_dossier(f"## Informe {i}\n\nTexto.")), range(10)))

    for i, pdf in enumerate(pdfs):
        assert f"Informe {i}" in PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
