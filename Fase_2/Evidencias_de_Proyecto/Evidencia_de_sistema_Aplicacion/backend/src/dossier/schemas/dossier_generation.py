"""Cuerpos de solicitud para generación de dossiers vía API."""
from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

DossierDepth = Literal["basic", "standard", "deep"]

# Alineado con el producto (créditos por profundidad).
DEPTH_CREDITS: dict[DossierDepth, int] = {
    "basic": 1,
    "standard": 3,
    "deep": 5,
}


class CorporateCompanyResolution(BaseModel):
    """Empresa elegida por el usuario tras desambiguar (registro UK o emisor SEC)."""

    source: Literal["companies_house", "sec_edgar"]
    title: str = Field(..., min_length=1, max_length=400)
    company_number: str | None = Field(
        default=None,
        max_length=20,
        description="Número Companies House (solo source=companies_house)",
    )
    ticker: str | None = Field(default=None, max_length=16, description="Ticker SEC")
    cik: str | None = Field(default=None, max_length=16, description="CIK SEC (10 dígitos)")

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, v: object) -> str:
        if v is None:
            raise ValueError("title requerido")
        s = str(v).strip()
        if not s:
            raise ValueError("title no puede estar vacío")
        return s

    @field_validator("company_number", "ticker", "cik", mode="before")
    @classmethod
    def strip_optional(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return str(v)

    @model_validator(mode="after")
    def validate_by_source(self) -> Self:
        if self.source == "companies_house":
            if not self.company_number:
                raise ValueError("company_number es obligatorio para companies_house")
        else:
            if not self.ticker or not self.cik:
                raise ValueError("ticker y cik son obligatorios para sec_edgar")
        return self


class CreateCorporateDossierRequest(BaseModel):
    """POST /dossiers/corporate/generate — agente corporativo (LangGraph UK + US + Gemini)."""

    subject_query: str = Field(
        min_length=2,
        max_length=500,
        description="Nombre, empresa o texto libre para el brief",
    )
    subject_email: str | None = Field(
        default=None,
        max_length=255,
        description="Email opcional del participante",
    )
    depth: DossierDepth = Field(
        default="standard",
        description="Profundidad (afecta créditos; el pipeline corporativo es el mismo)",
    )
    resolution: CorporateCompanyResolution | None = Field(
        default=None,
        description="Si el usuario eligió un registro concreto (UK o SEC), enriquece el prompt",
    )
    output_language: str | None = Field(
        default=None,
        max_length=16,
        description="Idioma del informe (es, en, pt, …). Desde Configuración del dashboard.",
    )

    @field_validator("subject_query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        return v.strip()

    @field_validator("subject_email", mode="before")
    @classmethod
    def empty_email_as_none(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return str(v).strip() if isinstance(v, str) else None


def build_corporate_generation_strings(
    body: CreateCorporateDossierRequest,
) -> tuple[str, str]:
    """
    Devuelve (participantes / brief para LangGraph, subject_name para la fila en DB).

    Si hay ``resolution``, el texto enviado al grafo incluye identificadores oficiales
    para reducir ambigüedad (p. ej. varias empresas llamadas «Ford»).
    """
    base = body.subject_query.strip()
    r = body.resolution
    if r is None:
        return base, base[:255]
    if r.source == "companies_house":
        cn = r.company_number or ""
        title = r.title.strip()
        participantes = (
            f"{title} — Reino Unido, empresa registrada en Companies House "
            f"(número {cn.strip()}). Petición del usuario (término buscado): «{base}»."
        )
        return participantes, title[:255]
    tk = (r.ticker or "").strip()
    ck = (r.cik or "").strip()
    title = r.title.strip()
    participantes = (
        f"{title} — Estados Unidos, emisor SEC (ticker {tk}, CIK {ck}). "
        f"Petición del usuario (término buscado): «{base}»."
    )
    return participantes, title[:255]
