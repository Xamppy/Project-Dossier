"""Plantillas de análisis Gemini para documentos regulatorios (Companies House y SEC EDGAR)."""
from __future__ import annotations

# Cuerpo común: lectura breve de riesgo sobre el documento (CH y SEC). Debe ser **corta** para no inflar el dossier.
_SHARED_CORPORATE_DOCUMENT_RISK_INSTRUCTIONS = """
Actúa como analista senior de riesgo, compliance y due diligence.

Analiza **solo** el documento y metadatos indicados. Objetivo: un informe **breve** (orientación: **600–900 palabras** como máximo), en Markdown, útil para dirección.

Cubre de forma compacta (sin repetir teoría ni rellenar):
- Qué hace la empresa y contexto del envío.
- Riesgos relevantes (financiero, reputacional, regulatorio, operacional, AML si aplica) con severidad **Alta / Media / Baja** solo donde aporte.
- Red flags concretas si existen.
- Una **clasificación global de riesgo** (Bajo / Medio / Alto / Crítico) en **una frase** con justificación breve.
- **3 a 5** acciones o comprobaciones concretas a priorizar.

Estructura sugerida (secciones cortas, pocas viñetas cada una):
## Resumen
## Riesgos y señales
## Clasificación de riesgo
## Próximos pasos

Requisitos:
- Lenguaje profesional; evita tablas salvo que ahorren espacio.
- No inventes datos. Si algo no figura en el documento: «no consta en este documento».
- Redacción para **cliente final**: no menciones marcas de IA, APIs, protocolos técnicos, «fragmentos» ni limitaciones del software. Si falta detalle, indícalo como punto a **validar con la contraparte** o **pedir en data room**, no como fallo técnico.
""".strip()


def format_ch_filing_gemini_prompt(
    *,
    company_name: str,
    company_number: str,
    date: str,
    ftype: str,
    category: str,
    description: str,
) -> str:
    """
    Prompt usado al analizar con Gemini el primer documento descargable del historial CH.

    Debe coincidir con la configuración del CLI (`maybe_analyze_ch_filing_with_gemini`).
    """
    scope_footer = f"""
---
Alcance del documento (Companies House)

Estás analizando **un único envío (filing)** de Companies House y sus metadatos de catálogo. Muchos apartados del informe solo podrán completarse si constan en ese documento; si no aplican o no figuran, indica **«no consta en este formulario»** y no rellenes vacíos con suposiciones. No mezcles datos de otros envíos no adjuntos.

Metadatos del envío:
- Empresa: {company_name}
- Número de empresa: {company_number}
- Fecha: {date}
- Tipo de formulario: {ftype}
- Categoría: {category}
- Descripción (catálogo): {description}
""".strip()

    return f"{_SHARED_CORPORATE_DOCUMENT_RISK_INSTRUCTIONS}\n\n{scope_footer}"


def format_sec_filing_gemini_prompt(
    *,
    company_name: str,
    cik: str,
    ticker: str,
    form: str,
    filing_date: str,
    accession: str,
    document_name: str,
) -> str:
    """
    Misma lógica analítica que CH, aplicada a un documento HTML/PDF descargado de un filing SEC.

    Usado por el CLI SEC y por el pipeline corporativo LangGraph (contexto USA).
    """
    tk = (ticker or "").strip() or "(no indicado en metadatos)"
    scope_footer = f"""
---
Alcance del documento (SEC EDGAR)

Estás analizando **un único archivo** correspondiente a un envío público en EDGAR (SEC). Muchos apartados del informe solo podrán completarse si constan en ese documento; si no aplican o no figuran, indica **«no consta en este documento»** y no rellenes vacíos con suposiciones. No mezcles datos de otros accession numbers no adjuntos.

Metadatos del envío:
- Emisor: {company_name}
- CIK: {cik}
- Ticker (referencia): {tk}
- Formulario SEC: {form}
- Fecha de presentación: {filing_date}
- Accession number: {accession}
- Archivo analizado: {document_name}
""".strip()

    return f"{_SHARED_CORPORATE_DOCUMENT_RISK_INSTRUCTIONS}\n\n{scope_footer}"
