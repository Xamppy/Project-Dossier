"""Orquestación: investigación de persona con PDL (People Data Labs) o búsqueda web (IA)."""
from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

from dossier.llm.client import deepseek_api_key
from dossier.llm.common import normalize_person_report_text
from dossier.llm.structured_synthesis import StructuredSynthesisError
from dossier.news import agent as agente_noticias
from dossier.schemas.dossier_executive_payload import PressMention, SourceCitation, SourceType
from dossier.schemas.person_research import PersonResearchRequest, PersonResearchSource
from dossier.services.dossier_progress_model import (
    person_partial_markdown,
    person_partial_profiles,
)
from dossier.services.executive_markdown import render_executive_markdown
from dossier.services.lusha_profile_facts import (
    merge_lusha_profiles_facts,
)
from dossier.services.pdl_research import exception_reason, fetch_pdl_profiles
from dossier.services.person_gemini_analysis import (
    analyze_person_profile_bundle,
    analyze_person_profile_bundle_structured,
)
from dossier.services.person_gemini_web_research import analyze_person_with_google_search
from dossier.services.source_provenance import normalizar_procedencia_fuentes

logger = logging.getLogger(__name__)


def _s(v: str | None) -> str | None:
    if v is None:
        return None
    t = v.strip()
    return t or None


def _merge_geo(country: str | None, city: str | None) -> str | None:
    c = _s(country)
    ci = _s(city)
    if ci and c:
        return f"{ci}, {c}"
    return c or ci


def _filters_for_person_gemini(
    req: PersonResearchRequest, organization_context_block: str | None
) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "full_name": req.full_name,
        "job_area": req.job_area,
        "company": req.company,
        "country": req.country,
        "city": req.city,
        "extra_keywords": req.extra_keywords,
    }
    oc = (organization_context_block or "").strip()
    if oc:
        filters["contexto_organizacion_cliente"] = oc
    return filters


def _person_web_disabled() -> bool:
    return (os.getenv("DEEPSEEK_DISABLE_PERSON_WEB") or os.getenv("GEMINI_DISABLE_GOOGLE_SEARCH") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _person_web_always() -> bool:
    """Si true, ejecuta también DeepSeek web aunque PDL haya devuelto perfiles."""
    v = (os.getenv("DEEPSEEK_PERSON_WEB_ALWAYS") or os.getenv("GEMINI_PERSON_WEB_ALWAYS") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


# Tope de menciones de prensa por persona (las que van a la IA, a la tarjeta y a la base).
MAX_MENCIONES_PERSONA = 10
_ETAPA_PRENSA = "person.press_search"
_FORMAS_JURIDICAS = re.compile(
    r"[\s,]+(s\.?a\.?|s\.?p\.?a\.?|ltda\.?|inc\.?|corp\.?|corporation|ltd\.?|llc|plc|gmbh|ag|s\.?l\.?|nv|bv)$",
    re.IGNORECASE,
)


def _empresa_para_prensa(req: PersonResearchRequest, profiles: list[dict[str, Any]]) -> str | None:
    """Empresa declarada o, si no hay, la actual según PDL; sin la forma jurídica final."""
    empresa = _s(req.company)
    if not empresa:
        for perfil in profiles:
            datos = perfil.get("data") if isinstance(perfil, dict) else None
            nombre = str((datos or {}).get("job_company_name") or "").strip()
            if nombre:
                empresa = nombre
                break
    if not empresa:
        return None
    limpia = _FORMAS_JURIDICAS.sub("", empresa).strip(" ,.")
    return limpia or empresa


def _buscar_prensa(
    req: PersonResearchRequest,
    profiles: list[dict[str, Any]],
    fuentes: list[Any] | None,
    progress: Any,
) -> tuple[list[PressMention], int]:
    """Menciones de prensa de la persona y créditos extra de las fuentes que respondieron.

    Nombre exacto entre comillas y, si se conoce, la empresa: con un nombre común, sin
    empresa, el filtro de homónimos exige todas las palabras del nombre.
    """
    if not fuentes:
        progress.stage(_ETAPA_PRENSA, "skipped", "feature_disabled")
        return [], 0
    nombre = " ".join(req.full_name.split())
    empresa = _empresa_para_prensa(req, profiles)
    consulta = f'"{nombre}"' + (f' "{empresa}"' if empresa else "")
    progress.stage(_ETAPA_PRENSA, "running")
    try:
        resultado = agente_noticias.collect_press_mentions(consulta, fuentes=fuentes)
    except Exception as exc:
        logger.warning("Fallo la búsqueda de prensa de la persona", exc_info=True)
        progress.stage(_ETAPA_PRENSA, "failed", exception_reason(exc))
        return [], 0
    detalle = [f for f in (getattr(resultado, "fuentes", None) or []) if f.estado != "limite_diario"]
    if not resultado.mentions and detalle and all(f.estado == "error" for f in detalle):
        progress.stage(_ETAPA_PRENSA, "failed", agente_noticias.motivo_de_fallo(resultado))
        return [], 0
    menciones, descartadas = agente_noticias.filtrar_homonimos(
        resultado.mentions, nombre, [empresa] if empresa else []
    )
    if descartadas:
        logger.info("Prensa de persona: %d menciones homónimas descartadas", descartadas)
    menciones = menciones[:MAX_MENCIONES_PERSONA]
    progress.stage(_ETAPA_PRENSA, "completed", None if menciones else "no_matches")
    return menciones, int(getattr(resultado, "creditos_extra_usados", 0) or 0)


def _citas_de_prensa(menciones: list[PressMention]) -> list[SourceCitation]:
    """Una cita por fuente de prensa que aportó menciones (procedencia del informe)."""
    vistas: dict[tuple[str, str], SourceCitation] = {}
    for m in menciones:
        vistas.setdefault((m.source.source_type.value, m.source.source_name), m.source)
    return list(vistas.values())


def _synthesize_person_report(
    *,
    filters: dict[str, Any],
    profiles: list[dict[str, Any]],
    meeting_context: dict[str, Any] | None,
    verified_facts: dict[str, Any],
    output_language: str,
    warnings: list[str],
    fuentes_consultadas: list[SourceCitation],
    progress: Any,
    menciones_prensa: list[PressMention] | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Una llamada JSON (S4.2) con el Markdown derivado por código.

    Si el JSON no valida tras el reintento asistido, se genera el informe Markdown
    de siempre. Los errores del proveedor no se reintentan aquí: fallarían igual.
    ``progress`` recibe la síntesis y, solo si de verdad se invoca, el respaldo.
    """
    progress.stage("person.profile_synthesis", "running")
    prensa_prompt = agente_noticias.menciones_para_prompt(menciones_prensa or []) or None
    try:
        payload = analyze_person_profile_bundle_structured(
            filters=filters,
            profiles=profiles,
            posts_by_url={},
            meeting_context=meeting_context,
            lusha_verified_facts=verified_facts,
            enrichment_provider="pdl",
            output_language=output_language,
            press_mentions=prensa_prompt,
        )
    except StructuredSynthesisError as e:
        progress.stage("person.profile_synthesis", "failed", "structured_output_invalid")
        logger.warning("La síntesis JSON no validó: %s", e)
        warnings.append("La síntesis JSON no validó; se generó el informe en Markdown.")
        progress.stage("person.markdown_fallback", "running")
        try:
            markdown = analyze_person_profile_bundle(
                filters=filters,
                profiles=profiles,
                posts_by_url={},
                meeting_context=meeting_context,
                lusha_verified_facts=verified_facts,
                enrichment_provider="pdl",
                output_language=output_language,
                press_mentions=prensa_prompt,
            )
        except Exception as exc:
            progress.stage("person.markdown_fallback", "failed", exception_reason(exc))
            raise
        if _valid_report(markdown):
            progress.stage("person.markdown_fallback", "completed")
            # El fallo original se conserva: el respaldo solo indica quién recuperó el informe.
            progress.stage(
                "person.profile_synthesis", "failed", recovered_by="person.markdown_fallback"
            )
        else:
            progress.stage("person.markdown_fallback", "failed", "no_valid_report")
        return markdown, None
    except Exception as exc:
        progress.stage("person.profile_synthesis", "failed", exception_reason(exc))
        progress.stage("person.markdown_fallback", "skipped", "not_required")
        raise
    # OE5/S4.7: el LLM no decide la procedencia. Se reescribe con las fuentes
    # realmente consultadas antes de renderizar el Markdown y de persistir el
    # payload, para que ambos coincidan.
    payload = normalizar_procedencia_fuentes(payload, fuentes_consultadas)
    if menciones_prensa:
        # UX-ADMIN-02: la prensa del informe es la que encontró el sistema, no la que redacte la IA.
        payload = payload.model_copy(update={"press_mentions": list(menciones_prensa)})
    markdown = render_executive_markdown(payload, output_language)
    progress.stage("person.profile_synthesis", "completed")
    progress.stage("person.markdown_fallback", "skipped", "not_required")
    return markdown, payload.model_dump(mode="json")


def _valid_report(text: str | None) -> bool:
    t = normalize_person_report_text(text)
    return t is not None and not t.lstrip().startswith("# Error")


def _context_skip_reason(*, applies: bool, has_llm_key: bool) -> str:
    if not applies:
        return "mode_not_applicable"
    if not has_llm_key:
        return "configuration_missing"
    return "feature_disabled"


def run_person_research(
    req: PersonResearchRequest,
    *,
    organization_context_block: str | None = None,
    meeting_context: dict[str, Any] | None = None,
    output_language: str | None = None,
    progress: Any = None,
    fuentes_prensa: list[Any] | None = None,
) -> dict[str, Any]:
    """Investiga una persona. ``progress`` (S5.10) es el scope ``person:N`` del job.

    ``fuentes_prensa`` (UX-ADMIN-02): fuentes de noticias que dejó el administrador; sin
    ellas la etapa de prensa se omite.

    Recibe las etapas que de verdad corren, en su orden real. La caché y el
    guardado los informa el wrapper que llama (manual o calendario).
    """
    from dossier.services.dossier_job_progress import NULL_SCOPE
    from dossier.services.output_language import normalize_output_language

    progress = progress if progress is not None else NULL_SCOPE
    out_lang = normalize_output_language(output_language or req.output_language)
    warnings: list[str] = []
    gemini_only = req.research_source == PersonResearchSource.gemini_web
    research_mode: str = "gemini_web" if gemini_only else "pdl_plus_gemini"

    attempts: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    profile_urls: list[str] = []
    source_citations: list[SourceCitation] = []

    if not gemini_only:
        profiles, attempts, pdl_warnings = fetch_pdl_profiles(req, progress=progress)
        warnings.extend(pdl_warnings)
        if profiles:
            progress.stage("person.profile_normalization", "running")
            # OE5/S4.7: la hora de consulta la fija el código al momento de
            # llamar a PDL, no el LLM de síntesis (que la inventaría).
            source_citations.append(
                SourceCitation(
                    source_type=SourceType.pdl,
                    source_name="People Data Labs",
                    retrieved_at=datetime.now(UTC),
                    url=None,
                    record_id=None,
                )
            )
        for p in profiles:
            profile_urls.extend(u for u in (p.get("linkedin_urls") or []) if u not in profile_urls)
        if profiles:
            # Los perfiles permitidos se publican antes de cualquier llamada al LLM (BE11).
            progress.partial(
                person_partial_profiles("person.profile_normalization", profiles, origin="generated")
            )
            progress.stage("person.profile_normalization", "completed")
        else:
            progress.stage("person.profile_normalization", "skipped", "no_profiles")

    if req.include_posts and not gemini_only:
        warnings.append("La opción «incluir posts» no está disponible; se ignoró.")

    menciones_prensa, extra_prensa = _buscar_prensa(req, profiles, fuentes_prensa, progress)
    source_citations.extend(_citas_de_prensa(menciones_prensa))
    prensa_prompt = agente_noticias.menciones_para_prompt(menciones_prensa) or None

    llm_md: str | None = None
    executive_payload: dict[str, Any] | None = None
    gemini_google_search_used = False
    has_llm_key = bool(deepseek_api_key())
    filters_gem = _filters_for_person_gemini(req, organization_context_block)
    verified_facts = merge_lusha_profiles_facts(profiles) if profiles else {}

    md_web: str | None = None
    web_applies = gemini_only or (not profiles) or _person_web_always()
    run_web = has_llm_key and not _person_web_disabled() and web_applies
    if run_web and profiles and not gemini_only and not _person_web_always():
        run_web = False
    context_done = False
    if run_web:
        # Una llamada a DeepSeek sin buscador (nombre histórico): no es una búsqueda web.
        progress.stage("person.context_analysis", "running")
        try:
            md_web = analyze_person_with_google_search(
                filters=filters_gem,
                meeting_context=meeting_context,
                output_language=out_lang,
                press_mentions=prensa_prompt,
            )
            gemini_google_search_used = True
        except RuntimeError as e:
            warnings.append(str(e))
            progress.stage("person.context_analysis", "failed", exception_reason(e))
        except Exception as e:
            # S7.2: el detalle técnico al log, no a los avisos que llegan al navegador.
            logger.warning("Error en análisis complementario con DeepSeek", exc_info=True)
            warnings.append("Error en análisis complementario con DeepSeek.")
            progress.stage("person.context_analysis", "failed", exception_reason(e))
        else:
            contexto = normalize_person_report_text(md_web)
            if _valid_report(contexto):
                progress.partial(
                    person_partial_markdown(
                        "person.context_analysis",
                        "person_context_report",
                        contexto,
                        basis="model_only",
                        sources=[],
                        origin="generated",
                    )
                )
                progress.stage("person.context_analysis", "completed")
                context_done = True
            else:
                progress.stage("person.context_analysis", "failed", "no_valid_report")
    else:
        progress.stage(
            "person.context_analysis",
            "skipped",
            _context_skip_reason(applies=bool(web_applies), has_llm_key=has_llm_key),
        )

    if gemini_only:
        if md_web:
            llm_md = md_web
        elif not has_llm_key:
            warnings.append(
                "Sin DEEPSEEK_API_KEY no se puede ejecutar la búsqueda por IA."
            )
        elif _person_web_disabled():
            warnings.append(
                "DEEPSEEK_DISABLE_PERSON_WEB=1: con «búsqueda por IA» no hay otra fuente; no se generó informe."
            )
    elif profiles and not has_llm_key:
        warnings.append(
            "DEEPSEEK_API_KEY no configurada: se omitió el análisis con IA sobre los datos encontrados."
        )
        progress.stage("person.profile_synthesis", "skipped", "configuration_missing")
        progress.stage("person.markdown_fallback", "skipped", "not_required")
    elif profiles:
        try:
            llm_md, executive_payload = _synthesize_person_report(
                filters=filters_gem,
                profiles=profiles,
                meeting_context=meeting_context,
                verified_facts=verified_facts,
                output_language=out_lang,
                warnings=warnings,
                fuentes_consultadas=source_citations,
                progress=progress,
                menciones_prensa=menciones_prensa,
            )
            if md_web and not llm_md:
                llm_md = md_web
            elif md_web and llm_md:
                warnings.append(
                    "Búsqueda web complementaria omitida: el análisis principal "
                    "ya incluye la estructura completa."
                )
        except RuntimeError as e:
            warnings.append(str(e))
        except Exception:
            logger.warning("Error en análisis sobre perfiles", exc_info=True)
            warnings.append("Error en análisis sobre perfiles.")
        if llm_md is None and md_web:
            llm_md = md_web
    elif not gemini_only and not profiles:
        progress.stage("person.profile_synthesis", "skipped", "no_profiles")
        progress.stage("person.markdown_fallback", "skipped", "not_required")
        if md_web:
            llm_md = md_web
        elif not has_llm_key:
            warnings.append(
                "Sin datos de enriquecimiento y sin DEEPSEEK_API_KEY: no se pudo ejecutar el análisis con IA."
            )
        elif _person_web_disabled():
            warnings.append(
                "Sin datos de enriquecimiento y DEEPSEEK_DISABLE_PERSON_WEB=1: no se ejecutó el análisis con IA."
            )

    llm_md = normalize_person_report_text(llm_md)
    _finalize_report(progress, llm_md, from_context=bool(md_web) and llm_md == normalize_person_report_text(md_web))
    if context_done:
        progress.stage(
            "person.context_analysis",
            "completed",
            used_in_final=bool(md_web) and llm_md == normalize_person_report_text(md_web),
        )

    return {
        "filters_applied": {
            "full_name": req.full_name,
            "job_area": req.job_area,
            "company": req.company,
            "email": req.email,
            "linkedin_url": req.linkedin_url,
            "country": req.country,
            "city": req.city,
            "extra_keywords": req.extra_keywords,
            "contexto_organizacion_cliente": (organization_context_block or "").strip()
            or None,
            "geo_effective": _merge_geo(req.country, req.city),
            "start": req.start,
            "max_profiles": req.max_profiles,
            "reveal_contact_details": req.reveal_contact_details,
            "include_posts": req.include_posts,
            "research_source": req.research_source.value,
            "research_mode": research_mode,
            "output_language": out_lang,
            "enrichment_provider": "pdl" if not gemini_only else None,
            "pdl_used": not gemini_only,
            "profiles_count": len(profiles),
            "verified_facts": verified_facts if profiles else None,
            "lusha_verified_facts": verified_facts if profiles else None,
        },
        "search_attempts": attempts,
        "profile_urls": profile_urls[: req.max_profiles],
        "profiles": profiles,
        "posts_by_url": {},
        "llm_analysis_markdown": llm_md,
        "executive_payload": executive_payload,
        "gemini_google_search_used": gemini_google_search_used,
        "warnings": warnings,
        # UX-ADMIN-02: prensa encontrada (para la tarjeta y la procedencia) y su cobro extra.
        "press_mentions": [m.model_dump(mode="json") for m in menciones_prensa],
        "press_query": req.full_name.strip(),
        "news_extra_credits": extra_prensa,
    }


def _finalize_report(progress: Any, report: str | None, *, from_context: bool) -> None:
    """Etapa ``person.report_finalize`` y el informe preliminar, antes de guardar."""
    if not report:
        progress.stage("person.report_finalize", "skipped", "no_content")
        return
    if not _valid_report(report):
        progress.stage("person.report_finalize", "failed", "no_valid_report")
        return
    basis, sources = ("model_only", []) if from_context else ("provider_records", ["pdl"])
    progress.partial(
        person_partial_markdown(
            "person.report_finalize",
            "person_report",
            report,
            basis=basis,
            sources=sources,
            origin="generated",
        )
    )
    progress.stage("person.report_finalize", "completed")
