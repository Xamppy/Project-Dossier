"""
PDF del dossier (S6.1), adjunto al correo para leerlo sin entrar a la plataforma.

Sigue el formato del detalle web (``CorporateDossierDetailView``) en su tema claro: logo,
tarjeta con estado, idioma, nombre y fechas, «Informe generado por IA» con el Markdown del
informe, y las alertas al final. Los textos fijos son los de los catálogos del dashboard.

ReportLab es Python puro: no pide librerías del sistema en Render ni en Docker. Sus fuentes
estándar cubren Windows-1252; un emoji o un ideograma sale como ■, pero no rompe el PDF.
"""
from __future__ import annotations

import io
import json
import math
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from markdown_it import MarkdownIt
from markdown_it.token import Token
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    Image,
    Indenter,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from dossier.db.models import Dossier
from dossier.services.output_language import normalize_output_language
from dossier.utils.html_text import strip_html_to_plain_line

_LOGO = Path(__file__).resolve().parent.parent / "assets" / "tracelens-logo.png"
_MARKDOWN = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
_ESQUEMAS_CLICABLES = ("http://", "https://", "mailto:")
# Una fila de tabla no se parte entre páginas: si alguna celda pasaría de este alto (puntos;
# el marco útil mide ~740), la tabla se escribe como «encabezado: valor».
_FILA_MAXIMA = 480

# Tema claro de frontend/src/app/globals.css.
_TEXTO = colors.HexColor("#0a1428")
_SECUNDARIO = colors.HexColor("#152238")
_TENUE = colors.HexColor("#334e68")
_ACENTO = colors.HexColor("#0099c7")
_EXITO = colors.HexColor("#047857")
_BORDE = colors.HexColor("#d3d7de")
_SUPERFICIE = colors.HexColor("#f2f4f7")

_MESES = {
    "es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre",
    "en": "January February March April May June July August September October November December",
    "pt": "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro",
    "it": "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre",
    "fr": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre",
    "de": "Januar Februar März April Mai Juni Juli August September Oktober November Dezember",
}
_FORMATO_FECHA = {
    "es": "{d} de {m} de {y}",
    "en": "{m} {d}, {y}",
    "pt": "{d} de {m} de {y}",
    "it": "{d} {m} {y}",
    "fr": "{d} {m} {y}",
    "de": "{d}. {m} {y}",
}

# Mismos textos que el detalle web (detail.*, dossiers.status_complete) más el pie.
_TEXTOS: dict[str, dict[str, str]] = {
    "es": {
        "kind": "Dossier de persona",
        "complete": "Completo",
        "report_in": "Informe en español",
        "dates": "Creado {created} · Actualizado {updated}",
        "report_title": "Informe generado por IA",
        "alerts": "Alertas de riesgo",
        "footer": "TraceLens · Confidencial: no lo reenvíes fuera de tu organización.",
        "page": "Página {n} de {total}",
    },
    "en": {
        "kind": "People dossier",
        "complete": "Complete",
        "report_in": "Report in English",
        "dates": "Created {created} · Updated {updated}",
        "report_title": "AI-generated report",
        "alerts": "Risk alerts",
        "footer": "TraceLens · Confidential: do not forward outside your organization.",
        "page": "Page {n} of {total}",
    },
    "pt": {
        "kind": "Dossiê de pessoa",
        "complete": "Completo",
        "report_in": "Relatório em português",
        "dates": "Criado {created} · Atualizado {updated}",
        "report_title": "Relatório gerado por IA",
        "alerts": "Alertas de risco",
        "footer": "TraceLens · Confidencial: não o reencaminhe para fora da sua organização.",
        "page": "Página {n} de {total}",
    },
    "it": {
        "kind": "Dossier persona",
        "complete": "Completato",
        "report_in": "Report in italiano",
        "dates": "Creato {created} · Aggiornato {updated}",
        "report_title": "Report generato da IA",
        "alerts": "Avvisi di rischio",
        "footer": "TraceLens · Riservato: non inoltrarlo al di fuori della tua organizzazione.",
        "page": "Pagina {n} di {total}",
    },
    "fr": {
        "kind": "Dossier personne",
        "complete": "Complet",
        "report_in": "Rapport en français",
        "dates": "Créé {created} · Mis à jour {updated}",
        "report_title": "Rapport généré par IA",
        "alerts": "Alertes de risque",
        "footer": "TraceLens · Confidentiel : ne le transférez pas hors de votre organisation.",
        "page": "Page {n} sur {total}",
    },
    "de": {
        "kind": "Personen-Dossier",
        "complete": "Abgeschlossen",
        "report_in": "Bericht auf Deutsch",
        "dates": "Erstellt {created} · Aktualisiert {updated}",
        "report_title": "KI-generierter Bericht",
        "alerts": "Risikowarnungen",
        "footer": "TraceLens · Vertraulich: nicht außerhalb Ihrer Organisation weiterleiten.",
        "page": "Seite {n} von {total}",
    },
}


def _estilos() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("cuerpo", fontName="Helvetica", fontSize=10, leading=14.5,
                          textColor=_SECUNDARIO, spaceAfter=6)
    return {
        "cuerpo": base,
        "item": ParagraphStyle("item", parent=base, spaceAfter=2),
        "cita": ParagraphStyle("cita", parent=base, textColor=_TENUE, fontName="Helvetica-Oblique"),
        "codigo": ParagraphStyle("codigo", parent=base, fontName="Courier", fontSize=8.5, leading=11.5,
                                 backColor=_SUPERFICIE, borderColor=_BORDE, borderWidth=0.5,
                                 borderPadding=6, spaceBefore=6, spaceAfter=10),
        "celda": ParagraphStyle("celda", parent=base, fontSize=8.8, leading=12, spaceAfter=0),
        "celda_th": ParagraphStyle("celda_th", parent=base, fontSize=8.8, leading=12, spaceAfter=0,
                                   fontName="Helvetica-Bold", textColor=_TEXTO),
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21,
                             textColor=_TEXTO, spaceBefore=12, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=14.5, leading=18,
                             textColor=_TEXTO, spaceBefore=11, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=12, leading=15,
                             textColor=_TEXTO, spaceBefore=9, spaceAfter=4),
        "h4": ParagraphStyle("h4", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                             textColor=_TEXTO, spaceBefore=8, spaceAfter=3),
        "seccion": ParagraphStyle("seccion", parent=base, fontName="Helvetica-Bold", fontSize=13,
                                  leading=16, textColor=_ACENTO, spaceBefore=14, spaceAfter=4),
        "nombre": ParagraphStyle("nombre", parent=base, fontName="Helvetica-Bold", fontSize=22,
                                 leading=27, textColor=_TEXTO, spaceBefore=6, spaceAfter=2),
        "dato": ParagraphStyle("dato", parent=base, fontSize=9.5, leading=13, textColor=_TENUE, spaceAfter=1),
        "fecha": ParagraphStyle("fecha", parent=base, fontSize=8.5, leading=12, textColor=_TENUE, spaceAfter=0),
        "tipo": ParagraphStyle("tipo", parent=base, fontSize=9, leading=12, textColor=_TENUE,
                               alignment=TA_RIGHT, spaceAfter=0),
        "insignia": ParagraphStyle("insignia", parent=base, fontName="Helvetica-Bold", fontSize=7.5,
                                   leading=9, spaceAfter=0),
    }


def _fecha(valor: datetime | None, lang: str) -> str:
    if valor is None:
        return "—"
    mes = _MESES[lang].split()[valor.month - 1]
    return _FORMATO_FECHA[lang].format(d=valor.day, m=mes, y=valor.year)


# --- Markdown → flowables de ReportLab ---------------------------------------------------


def _inline(children: list[Token] | None) -> str:
    """Marcado de párrafo de ReportLab. Todo el texto se escapa: ``<b>`` escrito en el
    informe se lee como texto, no como negrita."""
    partes: list[str] = []
    enlaces: list[bool] = []
    for t in children or []:
        if t.type == "text":
            partes.append(escape(t.content))
        elif t.type == "softbreak":
            partes.append(" ")
        elif t.type == "hardbreak":
            partes.append("<br/>")
        elif t.type == "strong_open":
            partes.append("<b>")
        elif t.type == "strong_close":
            partes.append("</b>")
        elif t.type == "em_open":
            partes.append("<i>")
        elif t.type == "em_close":
            partes.append("</i>")
        elif t.type == "s_open":
            partes.append("<strike>")
        elif t.type == "s_close":
            partes.append("</strike>")
        elif t.type == "code_inline":
            partes.append(f'<font face="Courier">{escape(t.content)}</font>')
        elif t.type == "link_open":
            href = str(t.attrGet("href") or "")
            clicable = href.lower().startswith(_ESQUEMAS_CLICABLES)
            enlaces.append(clicable)
            if clicable:
                partes.append(f'<a href="{escape(href, {chr(34): "&quot;"})}" color="#0099c7"><u>')
        elif t.type == "link_close":
            if enlaces and enlaces.pop():
                partes.append("</u></a>")
        elif t.type == "image":
            partes.append(f"<i>{escape(t.content)}</i>")
    return "".join(partes)


def _bloques(tokens: list[Token], i: int, fin: str | None, est: dict, parrafo: str = "cuerpo",
             nivel: int = 0) -> tuple[list[Flowable], int]:
    salida: list[Flowable] = []
    while i < len(tokens):
        t = tokens[i]
        if fin is not None and t.type == fin:
            return salida, i + 1
        if t.type == "heading_open":
            estilo = est.get(t.tag, est["h4"])
            salida.append(Paragraph(_inline(tokens[i + 1].children), estilo))
            i += 3
        elif t.type == "paragraph_open":
            salida.append(Paragraph(_inline(tokens[i + 1].children), est[parrafo]))
            i += 3
        elif t.type in ("bullet_list_open", "ordered_list_open"):
            lista, i = _lista(tokens, i, est, nivel)
            salida.append(lista)
        elif t.type == "table_open":
            tabla, i = _tabla(tokens, i, est)
            salida.extend(tabla)
        elif t.type == "blockquote_open":
            interior, i = _bloques(tokens, i + 1, "blockquote_close", est, "cita", nivel)
            salida.extend([Indenter(left=10), *interior, Indenter(left=-10)])
        elif t.type in ("fence", "code_block"):
            codigo = escape(t.content.rstrip("\n")).replace("\n", "<br/>")
            salida.append(Paragraph(codigo, est["codigo"]))
            i += 1
        elif t.type == "hr":
            salida.append(HRFlowable(width="100%", thickness=0.6, color=_BORDE, spaceBefore=6, spaceAfter=8))
            i += 1
        else:
            i += 1
    return salida, i


def _lista(tokens: list[Token], i: int, est: dict, nivel: int) -> tuple[Flowable, int]:
    apertura = tokens[i]
    ordenada = apertura.type == "ordered_list_open"
    fin = apertura.type.replace("_open", "_close")
    items: list[ListItem] = []
    i += 1
    while tokens[i].type != fin:
        if tokens[i].type == "list_item_open":
            interior, i = _bloques(tokens, i + 1, "list_item_close", est, "item", nivel + 1)
            items.append(ListItem(interior or [Paragraph("", est["item"])]))
        else:
            i += 1
    if ordenada:
        lista = ListFlowable(items, bulletType="1", start=int(apertura.attrGet("start") or 1),
                             leftIndent=16, bulletFontSize=9.5, bulletColor=_ACENTO)
    else:
        lista = ListFlowable(items, bulletType="bullet", start="•" if nivel == 0 else "–",
                             leftIndent=14, bulletFontSize=9.5, bulletColor=_ACENTO)
    return lista, i + 1


def _alto_estimado(texto: str, ancho_columna: float) -> float:
    """Alto aproximado de una celda: ~4,9 pt por carácter a 8,8 pt y 12 pt por línea."""
    por_linea = max(1.0, (ancho_columna - 10) / 4.9)
    return math.ceil(len(texto) / por_linea) * 12 + 8


def _tabla(tokens: list[Token], i: int, est: dict) -> tuple[list[Flowable], int]:
    filas: list[list[tuple[bool, str, str]]] = []
    fila: list[tuple[bool, str, str]] = []
    cabeceras = 0
    en_cabecera = False
    i += 1
    while tokens[i].type != "table_close":
        t = tokens[i]
        if t.type == "thead_open":
            en_cabecera = True
        elif t.type == "thead_close":
            en_cabecera = False
        elif t.type == "tr_open":
            fila = []
        elif t.type == "tr_close":
            filas.append(fila)
            cabeceras += 1 if en_cabecera else 0
        elif t.type in ("th_open", "td_open"):
            celda = tokens[i + 1]
            fila.append((t.type == "th_open", _inline(celda.children), celda.content))
            i += 2
        i += 1
    i += 1
    columnas = max((len(f) for f in filas), default=0)
    if columnas == 0:
        return [], i
    filas = [f + [(False, "", "")] * (columnas - len(f)) for f in filas]

    ancho = A4[0] - 36 * mm
    pesos = [max(6, min(40, max(len(f[c][2]) for f in filas))) for c in range(columnas)]
    anchos = [ancho * p / sum(pesos) for p in pesos]

    if any(_alto_estimado(c[2], a) > _FILA_MAXIMA for f in filas for c, a in zip(f, anchos, strict=True)):
        titulos = [c[1] for c in filas[0]] if cabeceras else [""] * columnas
        salida: list[Flowable] = []
        for f in filas[cabeceras:]:
            for titulo, (_, marcado, _texto) in zip(titulos, f, strict=True):
                salida.append(Paragraph(f"<b>{titulo}</b>: {marcado}" if titulo else marcado, est["cuerpo"]))
            salida.append(HRFlowable(width="100%", thickness=0.4, color=_BORDE, spaceAfter=6))
        return salida, i

    datos = [
        [Paragraph(c[1], est["celda_th"] if (c[0] or n < cabeceras) else est["celda"]) for c in f]
        for n, f in enumerate(filas)
    ]
    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.5, _BORDE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if cabeceras:
        estilo.append(("BACKGROUND", (0, 0), (-1, cabeceras - 1), _SUPERFICIE))
    tabla = Table(datos, colWidths=anchos, repeatRows=cabeceras, style=TableStyle(estilo), hAlign="LEFT")
    return [Spacer(1, 4), tabla, Spacer(1, 8)], i


# --- Documento -------------------------------------------------------------------------


def _insignia(texto: str, color: colors.Color, est: dict) -> Table:
    texto = texto.upper()
    estilo = ParagraphStyle("i", parent=est["insignia"], textColor=color)
    ancho = stringWidth(texto, estilo.fontName, estilo.fontSize) + 16
    return Table([[Paragraph(escape(texto), estilo)]], colWidths=[ancho], style=TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, color),
        ("ROUNDEDCORNERS", [7, 7, 7, 7]),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))


def _encabezado(dossier: Dossier, nombre: str, t: dict[str, str], lang: str, est: dict) -> list[Flowable]:
    ancho = A4[0] - 36 * mm
    logo = Image(str(_LOGO), width=46 * mm, height=46 * mm * 231 / 720, mask="auto")
    marca = Table([[logo, Paragraph(escape(t["kind"]), est["tipo"])]], colWidths=[ancho * 0.6, ancho * 0.4],
                  style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    estado, idioma = _insignia(t["complete"], _EXITO, est), _insignia(t["report_in"], _TENUE, est)
    insignias = Table([[estado, idioma]], colWidths=[estado._argW[0] + 6, idioma._argW[0] + 6],
                      hAlign="LEFT", style=TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                                       ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    tarjeta: list[Flowable] = [insignias, Paragraph(escape(nombre), est["nombre"])]
    if dossier.subject_email:
        tarjeta.append(Paragraph(escape(dossier.subject_email), est["dato"]))
    tarjeta.append(Paragraph(escape(t["dates"].format(
        created=_fecha(dossier.created_at, lang), updated=_fecha(dossier.updated_at or dossier.created_at, lang),
    )), est["fecha"]))
    caja = Table([[tarjeta]], colWidths=[ancho], style=TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, _BORDE),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    return [marca, Spacer(1, 3), HRFlowable(width="100%", thickness=2, color=_ACENTO, spaceAfter=10), caja]


def _seccion(titulo: str, est: dict) -> list[Flowable]:
    return [Paragraph(escape(titulo), est["seccion"]),
            HRFlowable(width="100%", thickness=0.6, color=_BORDE, spaceAfter=6)]


def _alertas(alertas: Any, t: dict[str, str], est: dict) -> list[Flowable]:
    if not isinstance(alertas, list) or not alertas:
        return []
    salida = _seccion(t["alerts"], est)
    for a in alertas:
        texto = a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)
        salida.append(Paragraph(escape(texto).replace("\n", "<br/>"), est["cuerpo"]))
    return salida


def _canvas_numerado(t: dict[str, str]) -> type[Canvas]:
    """Canvas que dibuja el pie con «Página n de N»: guarda cada página y pinta al final."""

    class CanvasNumerado(Canvas):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._paginas: list[dict] = []

        def showPage(self) -> None:
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._paginas)
            for estado in self._paginas:
                self.__dict__.update(estado)
                self._pie(total)
                super().showPage()
            super().save()

        def _pie(self, total: int) -> None:
            ancho, _ = A4
            self.setStrokeColor(_BORDE)
            self.setLineWidth(0.6)
            self.line(18 * mm, 14 * mm, ancho - 18 * mm, 14 * mm)
            self.setFont("Helvetica", 7.5)
            self.setFillColor(_TENUE)
            self.drawString(18 * mm, 9.5 * mm, t["footer"])
            self.drawRightString(ancho - 18 * mm, 9.5 * mm, t["page"].format(n=self._pageNumber, total=total))

    return CanvasNumerado


def render_dossier_pdf(dossier: Dossier, *, language: str | None = None) -> bytes:
    """PDF del dossier completo. ``ValueError`` si no tiene cuerpo."""
    data = dossier.dossier_data if isinstance(dossier.dossier_data, dict) else {}
    body = data.get("body")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("El dossier no tiene contenido para el PDF.")
    lang = normalize_output_language(language or data.get("output_language"))
    t = _TEXTOS[lang]
    est = _estilos()
    nombre = strip_html_to_plain_line(dossier.subject_name, max_len=255) or "Dossier"

    historia = _encabezado(dossier, nombre, t, lang, est)
    historia += _seccion(t["report_title"], est)
    informe, _ = _bloques(_MARKDOWN.parse(body), 0, None, est)
    historia += informe
    historia += _alertas(dossier.alerts, t, est)

    salida = io.BytesIO()
    doc = SimpleDocTemplate(
        salida, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
        title=f"Dossier: {nombre}", author="TraceLens", subject=t["report_title"], creator="TraceLens",
    )
    doc.build(historia, canvasmaker=_canvas_numerado(t))
    return salida.getvalue()


def dossier_pdf_filename(dossier: Dossier) -> str:
    """``dossier-<nombre-en-ascii>.pdf``: sin rutas, acentos ni caracteres raros."""
    nombre = strip_html_to_plain_line(dossier.subject_name or "", max_len=255)
    ascii_ = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-")[:60].strip("-")
    return f"dossier-{slug}.pdf" if slug else "dossier.pdf"
