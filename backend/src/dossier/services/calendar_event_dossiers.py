"""
Generación de dossiers desde eventos de calendario.

- **Empresa**: LangGraph corporativo → Companies House + SEC Edgar.
  Se detecta en el asunto; si no hay señal clara, en la descripción («Empresa: …»).
- **Persona** (descripción del evento): PDL + análisis IA.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from dossier.billing.credit_policy import PERSON_IDENTITY_CREDITS, credit_charging_enabled
from dossier.billing.entitlements import (
    corporate_dossier_module_flags,
    plan_allows_calendar_corporate_dossier,
)
from dossier.cache.corporate_dossier_redis import (
    build_corporate_langgraph_cache_key_hash,
    cached_until_from_now,
    corporate_cache_redis_key,
    get_corporate_cached_markdown,
    redis_corporate_cache_available,
    run_with_corporate_cache_lock,
    set_corporate_cached_markdown,
)
from dossier.cache.person_dossier_redis import (
    get_person_cached_payload,
    person_cache_redis_key,
    redis_person_cache_available,
    run_with_person_cache_lock,
    set_person_cached_payload,
)
from dossier.db.models import Dossier, User
from dossier.graphs.corporate_dossier_graph import (
    JurisdictionScope,
    run_corporate_dossier_langgraph_detailed,
)
from dossier.llm.common import normalize_person_report_text
from dossier.schemas.dossier_generation import DEPTH_CREDITS
from dossier.schemas.person_research import PersonResearchRequest, PersonResearchSource
from dossier.services.calendar_meeting_labels import (
    COUNTRY_IN_DESC,
    COUNTRY_INLINE_IN_JOB,
    EMAIL_IN_DESC,
    EMPRESA_DESC,
    JOB_IN_DESC,
    NUMBERED_CONTACT_PATTERNS,
    NUMBERED_COUNTRY,
    NUMBERED_EMAIL,
    NUMBERED_JOB,
    PERSON_LIST_LABEL,
    PERSON_PATTERNS,
    SUBJECT_CON,
)
from dossier.services.corporate_company_search import find_companies_house_matches, find_sec_matches
from dossier.services.dossier_job_progress import NULL_JOB_PROGRESS, NULL_SCOPE
from dossier.services.dossier_progress_model import (
    CORPORATE_AGENTS,
    corporate_partial,
    corporate_scope,
    person_scope,
)
from dossier.services.output_language import normalize_output_language
from dossier.services.person_dossier_dedup import (
    person_research_cache_payload_from_result,
    person_research_fingerprint,
    person_research_response_from_redis_cache,
    profiles_count_from_research_result,
    should_cache_person_research_result,
)
from dossier.services.person_research_config import default_person_research_source
from dossier.services.person_research_progress import (
    CACHE_LOOKUP,
    PERSIST,
    report_cache_hit,
    report_generated,
    report_persisted,
    scope_copy,
)
from dossier.services.person_research_service import run_person_research
from dossier.services.summary_cache import SUMMARY_CACHE
from dossier.utils.html_text import strip_html_to_plain_line, strip_html_to_text

logger = logging.getLogger(__name__)


_SUBJECT_PREFIX = re.compile(
    r"^(?:reunión|reunion|demo|llamada|call|meeting|segunda\s+reunión|primera\s+llamada)\s*"
    r"(?:comercial|producto|estratégica|estadategica|con|de)\s*[-–—:]\s*",
    re.IGNORECASE,
)

_SUBJECT_WITH = re.compile(
    r"(?i)^(?:reunión|reunion|demo|llamada|call|meeting)\s+(?:comercial|estratégica|estadategica|producto|con|de)\s+(.+)$"
)

_SUBJECT_CON = SUBJECT_CON

_EMPRESA_DESC = EMPRESA_DESC

_GENERIC_MEETING_TITLE = re.compile(
    r"(?i)^(?:reunión|reunion|meeting|call|llamada|demo|sync|standup|stand-up|daily|weekly|"
    r"kickoff|kick-off|1:1|one-on-one|catch-up|catchup|review|planning|genérico|generico|"
    r"réunion|reunião|reuniao|riunione|besprechung|termin)"
    r"(?:\s+(?:semanal|diaria|de\s+equipo|interna|internal|team|hebdomadaire|wöchentlich))?\s*$"
)

_PERSON_PATTERNS = PERSON_PATTERNS

_EMAIL_IN_DESC = EMAIL_IN_DESC

_JOB_IN_DESC = JOB_IN_DESC

_COUNTRY_IN_DESC = COUNTRY_IN_DESC

_NUMBERED_CONTACT_PATTERNS = NUMBERED_CONTACT_PATTERNS
_NUMBERED_JOB = NUMBERED_JOB
_NUMBERED_EMAIL = NUMBERED_EMAIL
_NUMBERED_COUNTRY = NUMBERED_COUNTRY

_OPTIONAL_FIELD_PLACEHOLDERS = frozenset(
    {
        "(país)",
        "(pais)",
        "(country)",
        "país",
        "pais",
        "country",
        "—",
        "-",
        "...",
        "n/a",
        "na",
        "s/n",
        "sin especificar",
        "not specified",
        "non spécifié",
        "non specifie",
        "não especificado",
        "nao especificado",
        "nicht angegeben",
        "non specificato",
    }
)


def _clean_optional_field(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().rstrip(".")
    if len(v) < 2:
        return None
    if v.lower() in _OPTIONAL_FIELD_PLACEHOLDERS:
        return None
    if v.startswith("(") and v.endswith(")"):
        return None
    return v


def extract_company_from_subject(tema: str) -> str:
    """Empresa en el asunto (p. ej. «Reunión comercial — Tesla Inc» o «Reunión con Tesla»)."""
    t = (tema or "").strip()
    if not t:
        return ""

    for sep in ("—", "–", " - ", ":"):
        if sep in t:
            parts = [p.strip() for p in t.split(sep) if p.strip()]
            if len(parts) >= 2:
                tail = parts[-1]
                if len(tail) >= 2:
                    return tail

    for pat in (_SUBJECT_WITH, _SUBJECT_CON):
        m = pat.match(t)
        if m:
            name = m.group(1).strip()
            if len(name) >= 2:
                return name

    cleaned = _SUBJECT_PREFIX.sub("", t).strip()
    return cleaned or t


def extract_company_from_description(descripcion: str) -> str:
    """Empresa en la descripción: «Empresa: …», «Company: …», etc."""
    d = (descripcion or "").strip()
    if not d:
        return ""

    m = _EMPRESA_DESC.search(d)
    if m:
        name = m.group(1).strip().rstrip(".")
        if len(name) >= 2:
            return name

    for line in d.splitlines():
        line = line.strip()
        if not line:
            continue
        extracted = extract_company_from_subject(line)
        if extracted and _subject_yields_company(line, extracted):
            return extracted

    return ""


def _subject_yields_company(tema: str, extracted: str) -> bool:
    """True si el asunto aporta un nombre de empresa (no solo el título genérico entero)."""
    if not extracted or len(extracted.strip()) < 2:
        return False
    t = (tema or "").strip().lower()
    e = extracted.strip().lower()
    if e == t:
        return False
    return not _GENERIC_MEETING_TITLE.match(extracted.strip())


def _description_signals_person_only(descripcion: str) -> bool:
    """Hay «Contacto:» (u otro campo persona) pero no «Empresa:» → solo dossier persona."""
    d = (descripcion or "").strip()
    if not d:
        return False
    has_person = bool(extract_numbered_persons_from_description(d)) or any(
        pat.search(d) for pat in _PERSON_PATTERNS
    )
    has_empresa = bool(_EMPRESA_DESC.search(d))
    return has_person and not has_empresa


# «Ana Pérez <ana@acme.test>»: nombre y correo entre <> al final del valor (BUG-2026-10-19-05).
_NAME_WITH_ANGLE_EMAIL = re.compile(r"^(?P<name>.*?)\s*<\s*(?P<email>[^<>\s@]+@[^<>\s@]+\.[^<>\s@]+)\s*>$")


def _split_name_and_email(value: str) -> tuple[str, str | None]:
    """
    Separa «Nombre <correo>» en (nombre, correo en minúsculas).

    Un nombre con el correo pegado degrada la búsqueda de la persona (PDL), así que el correo
    sale del nombre. Si lo que va entre <> no es un correo, o no queda nombre delante, el valor
    se devuelve tal cual y sin correo.
    """
    v = value.strip()
    m = _NAME_WITH_ANGLE_EMAIL.match(v)
    if not m or not m.group("name").strip():
        return v, None
    return m.group("name").strip(), m.group("email").lower()


def _indexed_fields(pattern: re.Pattern[str], text: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for m in pattern.finditer(text):
        idx = int(m.group(1))
        val = _clean_optional_field(m.group(2))
        if val:
            out[idx] = val
    return out


def extract_numbered_persons_from_description(descripcion: str) -> list[dict[str, Any]]:
    """
    Varios contactos numerados en la descripción::

        Contacto 1: Valeria Ruiz Prueba
        Cargo 1: CEO
        Email 1: valeria.ruiz@example.com
        Contacto 2: María López
        Cargo 2: CTO
    """
    d = (descripcion or "").strip()
    if not d:
        return []

    # «Contacto 1: Ana» y «Contacto 2 - Luis» pueden convivir; si un número se repite, gana «:».
    names: dict[int, str] = {}
    for pattern in _NUMBERED_CONTACT_PATTERNS:
        for idx, val in _indexed_fields(pattern, d).items():
            names.setdefault(idx, val)
    if not names:
        return []

    jobs = _indexed_fields(_NUMBERED_JOB, d)
    emails = _indexed_fields(_NUMBERED_EMAIL, d)
    countries = _indexed_fields(_NUMBERED_COUNTRY, d)

    persons: list[dict[str, Any]] = []
    for idx in sorted(names.keys()):
        name, angle_email = _split_name_and_email(names[idx])
        if len(name) < 2:
            continue
        job, country = _split_job_and_country(jobs.get(idx), countries.get(idx))
        email = emails.get(idx)
        if email:
            email = email.strip().lower()
            if "@" not in email:
                email = None
        # «Email N:» explícito manda; si no hay, vale el correo de «Contacto N: Nombre <correo>».
        email = email or angle_email
        persons.append(
            {
                "index": idx,
                "full_name": name,
                "job_area": job,
                "country": country,
                "email": email,
            }
        )
    return persons


def extract_all_persons_from_description(
    descripcion: str,
    tema: str = "",
) -> list[dict[str, Any]]:
    """
    Lista de contactos, en este orden de preferencia:

    1. Numerados («Contacto 1:», «Contacto 2:»), cada uno con su «Cargo N:», «Email N:», «País N:».
    2. Una lista con etiqueta en plural («Contactos: Ana Pérez, Luis Soto»): la coma o el punto y
       coma separan personas. Con dos o más, nadie hereda «Cargo:», «País:» ni «Email:» sin
       número, porque no se sabe de quién son; con una sola, se comporta como «Contacto:».
    3. Un único «Contacto:» (ver `extract_person_from_description`).
    """
    numbered = extract_numbered_persons_from_description(descripcion)
    if numbered:
        return numbered

    names = extract_person_list_from_description(descripcion)
    if len(names) > 1:
        # Cada «Nombre <correo>» de la lista conserva su propio correo; «Email:» suelto no se reparte.
        persons: list[dict[str, Any]] = []
        for idx, raw in enumerate(names, start=1):
            name, angle_email = _split_name_and_email(raw)
            persons.append(
                {"index": idx, "full_name": name, "job_area": None, "country": None, "email": angle_email}
            )
        return persons

    name, job, country, angle_email = _extract_person_fields(descripcion)
    if not name:
        name = extract_person_from_subject(tema)
    if not name or len(name) < 2:
        return []

    # «Email:» explícito manda; si no hay, vale el correo de «Contacto: Nombre <correo>».
    email = extract_email_from_description(descripcion) or angle_email
    return [
        {
            "index": 1,
            "full_name": name,
            "job_area": job,
            "country": country,
            "email": email,
        }
    ]


def extract_person_from_subject(tema: str) -> str:
    """Persona en asunto «Reunión con Ana García» (sin dossier corporativo)."""
    m = _SUBJECT_CON.match((tema or "").strip())
    if not m:
        return ""
    name = m.group(1).strip().rstrip(".")
    if len(name) < 2 or _GENERIC_MEETING_TITLE.match(name):
        return ""
    return name


def resolve_corporate_company(tema: str, descripcion: str) -> tuple[str, str]:
    """
    Empresa para dossier corporativo: primero asunto; si no hay señal clara, descripción.
    Devuelve (nombre, origen: subject|description|"").
    """
    if _description_signals_person_only(descripcion):
        return "", ""

    from_subject = extract_company_from_subject(tema)
    from_description = extract_company_from_description(descripcion)

    # «Reunión con {nombre}» sin «Empresa:» en descripción → no es brief corporativo.
    if _SUBJECT_CON.match((tema or "").strip()) and not from_description:
        return "", ""

    if from_description:
        return from_description.strip(), "description"
    if _subject_yields_company(tema, from_subject):
        return from_subject.strip(), "subject"
    if from_subject.strip():
        return from_subject.strip(), "subject"
    return "", ""


def _split_job_and_country(job_raw: str | None, country: str | None) -> tuple[str | None, str | None]:
    """«Cargo: Gerente País: Chile» en una línea → cargo y país separados."""
    job = _clean_optional_field(job_raw)
    if not job:
        return None, country
    m = COUNTRY_INLINE_IN_JOB.search(job)
    if m:
        parsed_country = _clean_optional_field(m.group(1))
        parsed_job = _clean_optional_field(job[: m.start()])
        return parsed_job, parsed_country or country
    return job, country


_PERSON_LIST_SEPARATOR = re.compile(r"[,;]")


def _first_person_match(descripcion: str) -> re.Match[str] | None:
    """Primer campo persona según el orden de `PERSON_PATTERNS`."""
    for pat in _PERSON_PATTERNS:
        m = pat.search(descripcion)
        if m:
            return m
    return None


def _is_person_list_match(match: re.Match[str]) -> bool:
    return bool(PERSON_LIST_LABEL.match(match.group(0)))


def _split_person_list(chunk: str) -> list[str]:
    """«Ana Pérez, , Luis Soto.» → ["Ana Pérez", "Luis Soto"]; descarta trozos de menos de 2 letras."""
    names: list[str] = []
    for part in _PERSON_LIST_SEPARATOR.split(chunk):
        name = part.strip().rstrip(".").strip()
        if len(name) >= 2:
            names.append(name)
    return names


def extract_person_list_from_description(descripcion: str) -> list[str]:
    """
    Nombres de una lista con etiqueta en plural: «Contactos: Ana Pérez, Luis Soto».

    Devuelve [] si el campo persona no usa una etiqueta en plural (`PERSON_LIST_LABELS`).
    """
    d = (descripcion or "").strip()
    if not d:
        return []
    m = _first_person_match(d)
    if not m or not _is_person_list_match(m):
        return []
    return _split_person_list(m.group(1).strip())


def extract_person_from_description(descripcion: str) -> tuple[str, str | None, str | None]:
    """
    Contacto, cargo y país opcional en la descripción.

    Formato recomendado (una línea por campo)::

        Empresa: Empresa Ejemplo SpA
        Contacto: Valeria Ruiz Prueba
        Cargo: CEO
        País (opcional): Estados Unidos

    «Contacto: Ana Pérez <ana@acme.test>» da el nombre sin el correo; el correo lo recoge
    `extract_all_persons_from_description`.

    Reglas de la coma en el valor del contacto (BUG-2026-10-19-06):

    - Etiqueta singular («Contacto:», «Nombre:», «Contact:»): «Nombre, Cargo». «Contacto: Ana
      Pérez, CEO» da nombre «Ana Pérez» y cargo «CEO», salvo que ya haya un «Cargo:»; entonces
      la coma se queda en el nombre.
    - Etiqueta plural («Contactos:», «Contacts:», «Contatos:», «Contatti:», «Kontakte:»): la coma
      o el punto y coma separan personas; aquí se devuelve la primera, sin cargo sacado de la
      coma. La lista completa la da `extract_all_persons_from_description`.

    Una etiqueta vacía no toma como valor la línea siguiente si esa línea es otra etiqueta
    («Contacto:\\nCargo: CEO» no tiene contacto).
    """
    name, job, country, _angle_email = _extract_person_fields(descripcion)
    return name, job, country


def _extract_person_fields(descripcion: str) -> tuple[str, str | None, str | None, str | None]:
    """(nombre, cargo, país, correo entre <> del contacto) de un único «Contacto:»."""
    d = (descripcion or "").strip()
    if not d:
        return "", None, None, None

    name = ""
    job: str | None = None
    country: str | None = None

    jm = _JOB_IN_DESC.search(d)
    if jm:
        job = _clean_optional_field(jm.group(1))

    cm = _COUNTRY_IN_DESC.search(d)
    if cm:
        country = _clean_optional_field(cm.group(1))

    m = _first_person_match(d)
    if m:
        chunk = m.group(1).strip().rstrip(".")
        if _is_person_list_match(m):
            names = _split_person_list(chunk)
            name = names[0] if names else ""
        elif "," in chunk and not job:
            name, rest = chunk.split(",", 1)
            name = name.strip()
            job = _clean_optional_field(rest)
        else:
            name = chunk

    name, angle_email = _split_name_and_email(name)

    if not name:
        em = _EMAIL_IN_DESC.search(d)
        if em:
            email = em.group(1).strip().rstrip(".")
            if "@" in email:
                local = email.split("@", 1)[0]
                parts = [p for p in re.split(r"[._-]+", local) if p]
                if len(parts) >= 2:
                    name = " ".join(p[:1].upper() + p[1:].lower() for p in parts)

    job, country = _split_job_and_country(job, country)

    return name.strip(), job, country, angle_email


def extract_email_from_description(descripcion: str) -> str | None:
    """Email en la descripción: «Email: …» o «Email. …»."""
    d = (descripcion or "").strip()
    if not d:
        return None
    em = _EMAIL_IN_DESC.search(d)
    if not em:
        return None
    email = em.group(1).strip().rstrip(".")
    if "@" not in email:
        return None
    return email.lower()


def extract_corporate_emails_from_text(*texts: str | None) -> list[str]:
    """Emails en descripción, participantes u otro texto del evento."""
    from dossier.services.lusha_company import email_to_company_domain

    found: list[str] = []
    for raw in texts:
        if not raw:
            continue
        for match in re.findall(r"(?i)[\w.+-]+@[\w.-]+\.\w+", raw):
            em = match.strip().lower()
            if email_to_company_domain(em) and em not in found:
                found.append(em)
    return found


def _sanitize_reunion_text_fields(reunion: dict[str, Any]) -> dict[str, Any]:
    """Limpia HTML en asunto/descripción (Google Calendar y pegados desde Outlook)."""
    out = dict(reunion)
    tema = strip_html_to_plain_line(out.get("tema"))
    if tema:
        out["tema"] = tema
    desc = strip_html_to_text(out.get("descripcion"))
    if desc:
        out["descripcion"] = desc[:2000]
    return out


def parse_calendar_event_for_dossiers(reunion: dict[str, Any]) -> dict[str, Any]:
    reunion = _sanitize_reunion_text_fields(reunion)
    tema = (reunion.get("tema") or "").strip()
    descripcion = (reunion.get("descripcion") or "").strip()
    participantes = (reunion.get("participantes") or "").strip()
    company_subject = extract_company_from_subject(tema)
    company_corporate, company_corporate_source = resolve_corporate_company(tema, descripcion)
    company_person = (
        extract_company_from_description(descripcion)
        or company_corporate
        or (company_subject if company_corporate else "")
    )
    person_name, person_job, person_country = extract_person_from_description(descripcion)
    persons = extract_all_persons_from_description(descripcion, tema)
    first_person = persons[0] if persons else {}
    person_name = first_person.get("full_name") or person_name
    person_job = first_person.get("job_area") if persons else person_job
    person_country = first_person.get("country") if persons else person_country
    person_email = first_person.get("email")
    if not person_name:
        person_name = extract_person_from_subject(tema)
    if person_email is None:
        person_email = extract_email_from_description(descripcion)
    # Con un único contacto, el «Email:» sin número o el correo corporativo del evento es suyo.
    if len(persons) == 1 and not persons[0].get("email"):
        if not person_email:
            corp_emails = extract_corporate_emails_from_text(descripcion, participantes)
            person_email = corp_emails[0] if corp_emails else None
        if person_email:
            persons[0]["email"] = person_email
    if not persons and not person_name and descripcion:
        logger.info(
            "Calendario: descripción sin persona detectable (len=%s). "
            "Usa «Contacto:» / «Contacto 1:» o «Nombre:» en el cuerpo del evento.",
            len(descripcion),
        )
    return {
        "company": company_corporate,
        "company_subject": company_subject,
        "company_corporate": company_corporate,
        "company_corporate_source": company_corporate_source,
        "company_person": company_person,
        "persons": persons,
        "person_name": person_name,
        "person_job": person_job,
        "person_country": person_country,
        "person_email": person_email,
        "tema": tema,
        "descripcion": descripcion,
        "participantes": participantes,
    }


def resolve_corporate_brief(company_query: str) -> tuple[str, JurisdictionScope]:
    """
    Resuelve empresa en registro UK o SEC antes del LangGraph (evita homónimos y briefs ambiguos).
    """
    q = (company_query or "").strip()
    if len(q) < 2:
        return q, "dual"

    us_hits = find_sec_matches(q, limit=5)
    if us_hits:
        h = us_hits[0]
        title = h.get("title") or q
        ticker = h.get("ticker") or ""
        cik = h.get("cik") or ""
        brief = (
            f"{title} — Estados Unidos, emisor SEC (ticker {ticker}, CIK {cik}). "
            f"Petición del usuario (término buscado): «{q}»."
        )
        return brief, "us_only"

    uk_hits, _ = find_companies_house_matches(q, limit=5)
    if uk_hits:
        h = uk_hits[0]
        title = h.get("title") or q
        cn = h.get("company_number") or ""
        brief = (
            f"{title} — Reino Unido, empresa registrada en Companies House "
            f"(número {cn}). Petición del usuario (término buscado): «{q}»."
        )
        return brief, "uk_only"

    return q, "dual"


def _corporate_md_from_cache_or_langgraph(
    *,
    participantes_brief: str,
    tema: str,
    participantes: str,
    scope: JurisdictionScope,
    depth: str,
    output_language: str = "es",
    empresa_objetivo: str | None = None,
    progress: Any = None,
) -> tuple[str | None, bool, str | None, list[str] | None]:
    """Devuelve (markdown, cache_hit, cache_key_redis, agents_failed).

    ``agents_failed`` es ``None`` cuando el resultado viene de caché (no se corrió el
    grafo en esta llamada, así que no hay telemetría nueva de agentes) y una lista
    (posiblemente vacía) cuando sí se ejecutó LangGraph. ``progress`` es el scope
    corporativo del job (S5.10).
    """
    progress = progress if progress is not None else NULL_SCOPE
    out_lang = normalize_output_language(output_language)
    key_hash = build_corporate_langgraph_cache_key_hash(
        participantes=participantes_brief,
        jurisdiction_scope=scope,
        depth=depth,
        output_language=out_lang,
    )
    cache_hit = False
    md: str | None = None
    agents_failed: list[str] | None = None

    if redis_corporate_cache_available():
        hit = get_corporate_cached_markdown(key_hash)
        if hit is not None:
            _report_corporate_cache_hit(progress, hit)
            return hit, True, corporate_cache_redis_key(key_hash), None

    def _compute() -> None:
        nonlocal md, cache_hit, agents_failed
        hit2 = get_corporate_cached_markdown(key_hash)
        if hit2 is not None:
            md = hit2
            cache_hit = True
            _report_corporate_cache_hit(progress, hit2)
            return
        generado = run_corporate_dossier_langgraph_detailed(
            tema_reunion=tema or "Reunión",
            participantes=participantes_brief,
            descripcion="",
            jurisdiction_scope=scope,
            output_language=out_lang,
            empresa_objetivo=empresa_objetivo,
            progress=progress,
        )
        progress.fields(origin="generated")
        if not generado.markdown.lstrip().startswith("# Error"):
            set_corporate_cached_markdown(key_hash, generado.markdown)
        md = generado.markdown
        agents_failed = generado.agents_failed
        cache_hit = False

    run_with_corporate_cache_lock(key_hash, _compute)
    redis_key = corporate_cache_redis_key(key_hash) if cache_hit else None
    return md, cache_hit, redis_key, agents_failed


def _report_corporate_cache_hit(progress: Any, markdown: str) -> None:
    """Corporativo desde caché: ningún agente corrió en este job (sin historial inventado)."""
    for agente in CORPORATE_AGENTS:
        progress.agent(agente, "skipped", "cache_hit")
    progress.fields(origin="redis_cache")
    progress.partial(corporate_partial("synthesize_llm", "synthesis", markdown, origin="redis_cache"))


def _person_research_from_cache_or_pipeline(
    *,
    req: PersonResearchRequest,
    organization_id: UUID,
    organization_context_block: str | None,
    meeting_context: dict[str, Any],
    output_language: str = "es",
    progress: Any = None,
) -> tuple[dict[str, Any] | None, bool, str | None]:
    """Devuelve (payload, cache_hit, cache_key_redis). ``progress``: scope ``person:N`` (S5.10)."""
    progress = progress if progress is not None else NULL_SCOPE
    out_lang = normalize_output_language(output_language or req.output_language)
    fp = person_research_fingerprint(req, organization_id, output_language=out_lang)
    cache_hit = False
    cached_payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None

    redis_disponible = redis_person_cache_available()
    if redis_disponible:
        progress.stage(CACHE_LOOKUP, "running")
        hit = get_person_cached_payload(fp)
        if hit is not None:
            cached_payload = hit
            cache_hit = True
            progress.stage(CACHE_LOOKUP, "completed", "cache_hit")
    else:
        progress.stage(CACHE_LOOKUP, "skipped", "cache_unavailable")

    if not cache_hit:

        def _compute() -> None:
            nonlocal cache_hit, cached_payload, result
            h2 = get_person_cached_payload(fp)
            if h2 is not None:
                cached_payload = h2
                cache_hit = True
                progress.stage(CACHE_LOOKUP, "completed", "cache_hit")
                return
            if redis_disponible:
                progress.stage(CACHE_LOOKUP, "completed", "cache_miss")
            nr = run_person_research(
                req,
                organization_context_block=organization_context_block,
                meeting_context=meeting_context,
                output_language=out_lang,
                progress=progress,
            )
            result = nr
            md_new = (nr.get("llm_analysis_markdown") or "").strip()
            if should_cache_person_research_result(
                nr,
                gemini_only=req.research_source == PersonResearchSource.gemini_web,
            ):
                set_person_cached_payload(
                    fp,
                    {
                        "markdown": md_new,
                        "gemini_google_search_used": nr.get("gemini_google_search_used"),
                        **person_research_cache_payload_from_result(nr),
                    },
                )
            cache_hit = False

        run_with_person_cache_lock(fp, _compute)

    if cache_hit and cached_payload is not None:
        result = person_research_response_from_redis_cache(
            req,
            organization_context_block=organization_context_block,
            cached_payload=cached_payload,
        )
        report_cache_hit(progress, research_source=req.research_source.value, cached_payload=cached_payload)
    elif result is not None:
        report_generated(progress, result)

    redis_key = person_cache_redis_key(fp) if cache_hit else None
    return result, cache_hit, redis_key


def _generate_one_person_dossier(
    *,
    person: dict[str, Any],
    reunion: dict[str, Any],
    parsed: dict[str, Any],
    company_corporate: str,
    company_person: str,
    tema: str,
    participantes: str,
    organization_id: UUID | None,
    organization_context_block: str | None,
    output_language: str,
    progress: Any = None,
) -> dict[str, Any]:
    """Genera un dossier de persona para un contacto del evento. ``progress``: su scope (S5.10)."""
    progress = progress if progress is not None else NULL_SCOPE
    person_name = (person.get("full_name") or "").strip()
    person_job = person.get("job_area")
    person_country = person.get("country")
    # Solo el correo declarado para este contacto. El correo corporativo suelto del
    # evento ya se asigna en ``parse_calendar_event_for_dossiers`` cuando hay un único
    # contacto; con varios no se sabe de quién es, y consultar PDL con el de otro
    # asistente trae (y cobra) un perfil ajeno (BUG-2026-10-19-02).
    person_email = person.get("email") or None

    out: dict[str, Any] = {
        "index": person.get("index"),
        "full_name": person_name,
        "job_area": person_job,
        "country": person_country,
        "email": person_email,
        "md": None,
        "payload": None,
        "cache_hit": False,
        "cache_key": None,
        "error": None,
        "scope_id": progress.scope_id,
    }
    if len(person_name) < 2:
        return out

    try:
        meeting_ctx = {
            "tema": tema,
            "descripcion": parsed.get("descripcion") or (reunion.get("descripcion") or ""),
            "participantes": participantes,
            "empresa_reunion": company_corporate or company_person or None,
            "contacto_declarado": person_name,
            "cargo_declarado": person_job,
            "inicio": reunion.get("inicio"),
            "ubicacion": reunion.get("ubicacion"),
        }
        person_src = default_person_research_source()
        req = PersonResearchRequest(
            full_name=person_name,
            company=company_person or None,
            job_area=person_job,
            country=person_country,
            email=person_email,
            research_source=person_src,
            max_profiles=1,
            reveal_contact_details=False,
            output_language=output_language,
        )
        if organization_id is not None:
            person_payload, person_cache_hit, person_cache_key = _person_research_from_cache_or_pipeline(
                req=req,
                organization_id=organization_id,
                organization_context_block=organization_context_block,
                meeting_context=meeting_ctx,
                output_language=output_language,
                progress=progress,
            )
        else:
            progress.stage(CACHE_LOOKUP, "skipped", "cache_unavailable")
            person_payload = run_person_research(
                req,
                organization_context_block=organization_context_block,
                meeting_context=meeting_ctx,
                output_language=output_language,
                progress=progress,
            )
            report_generated(progress, person_payload)
            person_cache_hit = False
            person_cache_key = None
        out["md"] = (
            person_payload.get("llm_analysis_markdown") or ""  # type: ignore[union-attr]
        ).strip() or None
        out["payload"] = person_payload
        out["cache_hit"] = person_cache_hit
        out["cache_key"] = person_cache_key
    except Exception as e:
        logger.exception("Fallo dossier persona desde calendario (%s)", person_name)
        out["error"] = str(e)
        out["md"] = f"# Error en dossier persona\n\n{e}"
    return out


# Ayuda que ve el usuario cuando no se pudo generar ningún dossier. Datos ficticios.
MENSAJE_FORMATO_SIN_DOSSIER = (
    "No se pudo generar ningún dossier. "
    "Usa este formato en la descripción del evento:\n\n"
    "**Asunto:** Kick-off proyecto Q3\n\n"
    "**Descripción:**\n"
    "Empresa: Empresa Ejemplo SpA\n"
    "Contacto 1: Valeria Ruiz Prueba\n"
    "Cargo 1: CEO\n"
    "País 1: Estados Unidos\n"
    "Contacto 2: Andrea Soto Ejemplo\n"
    "Cargo 2: Presidenta"
)


def generate_dossiers_from_calendar_event(
    reunion: dict[str, Any],
    *,
    organization_context_block: str | None = None,
    organization_id: UUID | None = None,
    organization_plan: str | None = None,
    depth: str = "standard",
    output_language: str | None = None,
    progress: Any = None,
) -> dict[str, Any]:
    """
    Devuelve dossiers corporativo (CH/SEC) y de persona (PDL) por separado.

    En plan Free se omite el corporativo; el formato del evento es el mismo.
    ``progress`` (S5.10) es el ``JobProgress`` del job: se declaran un scope
    corporativo y uno por asistente con nombre válido, antes de ejecutar nada.
    """
    job_progress = progress if progress is not None else NULL_JOB_PROGRESS
    reunion = _sanitize_reunion_text_fields(reunion)
    out_lang = normalize_output_language(output_language)
    parsed = parse_calendar_event_for_dossiers(reunion)
    company_corporate = parsed["company_corporate"]
    company_person = parsed["company_person"]
    persons = parsed.get("persons") or []
    tema = parsed["tema"]
    participantes = parsed["participantes"]

    corporate_md: str | None = None
    dossier_personas: list[dict[str, Any]] = []
    person_md: str | None = None
    person_payload: dict[str, Any] | None = None
    errors: list[str] = []
    corporate_cache_hit = False
    person_cache_hit = False
    corporate_cache_key: str | None = None
    person_cache_key: str | None = None
    # None = sin telemetría de agentes (caché o rama no ejecutada); persist_calendar_dossiers
    # cae al criterio anterior (¿el markdown final es un error?) en ese caso.
    corporate_agents_failed: list[str] | None = None
    depth_key = depth if depth in DEPTH_CREDITS else "standard"
    include_corporate = plan_allows_calendar_corporate_dossier(organization_plan)
    corporate_skipped_plan_free = False

    # La modalidad de los asistentes la decide el servidor, no el formulario de Personas.
    fuente_personas = default_person_research_source().value
    scopes: list[dict[str, Any]] = [corporate_scope("corporate:0", company_corporate)] if company_corporate else []
    scope_por_persona: dict[int, str] = {}
    for i, person in enumerate(persons):
        nombre = (person.get("full_name") or "").strip()
        if len(nombre) >= 2:
            scope_por_persona[i] = f"person:{len(scope_por_persona)}"
            scopes.append(person_scope(scope_por_persona[i], nombre, fuente_personas))
    job_progress.declare(scopes)

    if company_corporate and include_corporate:
        try:
            participantes_brief, scope = resolve_corporate_brief(company_corporate)
            if participantes:
                participantes_brief = f"{participantes_brief} Asistentes: {participantes}"
            (
                corporate_md,
                corporate_cache_hit,
                corporate_cache_key,
                corporate_agents_failed,
            ) = _corporate_md_from_cache_or_langgraph(
                participantes_brief=participantes_brief,
                tema=tema,
                participantes=participantes_brief,
                scope=scope,
                depth=depth_key,
                output_language=out_lang,
                empresa_objetivo=company_corporate,
                progress=job_progress.scope("corporate:0"),
            )
        except Exception as e:
            logger.exception("Fallo dossier corporativo desde calendario")
            errors.append(f"Corporativo: {e}")
            corporate_md = f"# Error en dossier corporativo\n\n{e}"

    elif company_corporate and not include_corporate:
        corporate_skipped_plan_free = True
        for agente in CORPORATE_AGENTS:
            job_progress.scope("corporate:0").agent(agente, "skipped", "plan_not_included")

    for i, person in enumerate(persons):
        sid = scope_por_persona.get(i)
        one = _generate_one_person_dossier(
            person=person,
            reunion=reunion,
            parsed=parsed,
            company_corporate=company_corporate,
            company_person=company_person,
            tema=tema,
            participantes=participantes,
            organization_id=organization_id,
            organization_context_block=organization_context_block,
            output_language=out_lang,
            progress=job_progress.scope(sid) if sid else None,
        )
        dossier_personas.append(one)
        if one.get("error"):
            label = one.get("full_name") or f"Contacto {one.get('index') or '?'}"
            errors.append(f"Persona ({label}): {one['error']}")
        if person_md is None and one.get("md"):
            person_md = one["md"]
            person_payload = one.get("payload")
            person_cache_hit = bool(one.get("cache_hit"))
            person_cache_key = one.get("cache_key")

    if not corporate_md and not any(p.get("md") for p in dossier_personas):
        corporate_md = MENSAJE_FORMATO_SIN_DOSSIER

    return {
        "reunion": reunion,
        "parse": parsed,
        "dossier_corporativo": corporate_md,
        "dossier_persona": person_md,
        "dossier_persona_research": person_payload,
        "dossier_personas": dossier_personas,
        "dossier_generado": corporate_md or person_md or "",
        "errors": errors,
        "corporate_cache_hit": corporate_cache_hit,
        "person_cache_hit": person_cache_hit,
        "corporate_cache_key": corporate_cache_key,
        "person_cache_key": person_cache_key,
        "corporate_agents_failed": corporate_agents_failed,
        "output_language": out_lang,
        "corporate_skipped_plan_free": corporate_skipped_plan_free,
    }


def _markdown_is_persistable(md: str | None) -> bool:
    if normalize_person_report_text(md) is None:
        return False
    s = (md or "").lstrip()
    if s.startswith("# Error"):
        return False
    return not s.startswith("No se pudo generar ningún dossier")


def _is_technical_warning(text: str) -> bool:
    """Avisos de configuración/infra que no deben mostrarse al usuario final."""
    t = text.strip().lower()
    if not t:
        return True
    markers = (
        ".env",
        "api_key",
        "deepseek",
        "gemini",
        "pdl_api",
        "people data labs",
        "dashboard →",
        "dashboard ->",
        "postgresql",
        "migracion",
        "jwt_secret",
        "sin perfiles de pdl",
        "no se pudo ejecutar el análisis con ia",
    )
    return any(m in t for m in markers)


def _person_failure_message(
    *,
    person_payload: dict[str, Any] | None,
    errors: list[Any] | None,
    person_md: str | None,
) -> str:
    if person_md:
        s = person_md.lstrip()
        if s.startswith("# Error"):
            parts = s.split("\n", 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()[:500]
            return "Error al generar el análisis de persona."

    warnings = (person_payload or {}).get("warnings") if isinstance(person_payload, dict) else []
    if isinstance(warnings, list) and warnings:
        parts = [str(w).strip() for w in warnings if w and str(w).strip()]
        user_parts = [p for p in parts if not _is_technical_warning(p)]
        if user_parts:
            return "; ".join(user_parts)[:500]

    persona_errors = [e for e in (errors or []) if "Persona" in str(e)]
    if persona_errors:
        return str(persona_errors[0])[:500]

    return (
        "No se pudo generar el análisis de persona. "
        "Reintenta la generación o usa «Nueva búsqueda de persona» con más datos."
    )


def _format_meeting_datetime(inicio: str | None, tz_name: str | None = None) -> str:
    if not inicio:
        return ""
    raw = inicio.strip()
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        tz_key = (tz_name or "UTC").strip() or "UTC"
        try:
            from zoneinfo import ZoneInfo

            local = dt.astimezone(ZoneInfo(tz_key))
        except Exception:  # noqa: BLE001 - fallback de timezone invalida a UTC
            local = dt.astimezone(UTC)
        return local.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return raw[:16]


def build_calendar_meeting_label(
    reunion: dict[str, Any],
    tz_name: str | None = None,
) -> str:
    """Etiqueta legible de la reunión (asunto + fecha/hora en zona del usuario)."""
    tema = (reunion.get("tema") or "").strip() or "Reunión"
    when = _format_meeting_datetime(reunion.get("inicio"), tz_name)
    if when:
        return f"{tema} · {when}"
    return tema


def _calendar_meta(
    reunion: dict[str, Any],
    provider: str,
    tz_name: str | None = None,
) -> dict[str, Any]:
    meeting_label = build_calendar_meeting_label(reunion, tz_name)
    return {
        "provider": provider,
        "external_event_id": reunion.get("id"),
        "tema": reunion.get("tema"),
        "inicio": reunion.get("inicio"),
        "fin": reunion.get("fin"),
        "participantes": reunion.get("participantes"),
        "meeting_label": meeting_label,
    }


def calendar_meeting_summary_from_dossier_data(
    dossier_data: dict[str, Any] | None,
    *,
    trigger_source: str | None = None,
    tz_name: str | None = None,
) -> str | None:
    """Etiqueta de reunión para listados (nuevos y dossiers ya guardados)."""
    if (trigger_source or "").strip() != "calendar":
        return None
    data = dossier_data if isinstance(dossier_data, dict) else {}
    cal = data.get("calendar")
    if not isinstance(cal, dict):
        return None
    reunion = {
        "tema": cal.get("tema"),
        "inicio": cal.get("inicio"),
    }
    if reunion.get("tema") or reunion.get("inicio"):
        built = build_calendar_meeting_label(reunion, tz_name)
        if built:
            return built[:255]
    label = cal.get("meeting_label")
    if isinstance(label, str) and label.strip():
        return label.strip()[:255]
    return None


def persist_calendar_dossiers(
    db: Session,
    *,
    user_id: UUID,
    org_id: UUID,
    result: dict[str, Any],
    calendar_provider: str,
    generation_duration_ms: int,
    calendar_event_id: UUID | None = None,
    depth: str = "standard",
    charge_credits: bool = True,
    trigger_source: str = "calendar",
    progress: Any = None,
) -> dict[str, Any]:
    """
    Guarda dossier corporativo y/o persona en ``dossiers`` (Mis Dossiers).

    Con ``progress`` (S5.10) cada dossier copia su scope en ``dossier_data["_progress"]``
    y, tras el commit, se cierra ``person.persist`` de cada asistente.
    """
    job_progress = progress if progress is not None else NULL_JOB_PROGRESS
    corporate_progress = job_progress.scope("corporate:0")
    guardados_persona: list[tuple[Any, str, str]] = []
    parsed = result.get("parse") or {}
    reunion = result.get("reunion") or {}
    user_row = db.get(User, user_id) if user_id else None
    user_tz = getattr(user_row, "timezone", None) if user_row else None
    cal = _calendar_meta(reunion, calendar_provider, user_tz)
    now = datetime.now(UTC)
    saved: dict[str, Any] = {}
    folder_id = uuid.uuid4()
    folder_title = (
        cal.get("meeting_label")
        or (parsed.get("tema") or "").strip()
        or (parsed.get("company_corporate") or "").strip()
        or "Reunión"
    )
    folder_title = strip_html_to_plain_line(folder_title, max_len=255) or "Reunión"
    calendar_folder = {"id": str(folder_id), "title": folder_title}
    depth_key = depth if depth in DEPTH_CREDITS else "standard"
    charge = charge_credits and credit_charging_enabled()
    corp_cost = DEPTH_CREDITS[depth_key]
    person_cost = PERSON_IDENTITY_CREDITS
    corporate_cache_hit = bool(result.get("corporate_cache_hit"))
    person_cache_hit = bool(result.get("person_cache_hit"))
    cache_expires = cached_until_from_now()
    output_lang = normalize_output_language(result.get("output_language"))

    corporate_md = result.get("dossier_corporativo")
    if _markdown_is_persistable(corporate_md):
        is_err = str(corporate_md).lstrip().startswith("# Error")
        status = "failed" if is_err else "complete"
        # Telemetría real del grafo si se ejecutó en esta llamada (S4.9); si vino de
        # caché o de una excepción fuera del grafo, cae al criterio anterior.
        explicit_agents_failed = result.get("corporate_agents_failed")
        corp_agents_failed = (
            list(explicit_agents_failed)
            if explicit_agents_failed is not None
            else (["synthesize_llm"] if is_err else [])
        )
        will_charge_corp = charge and not is_err and not corporate_cache_hit
        dossier_id = uuid.uuid4()
        subject = (
            parsed.get("company_corporate")
            or parsed.get("company")
            or parsed.get("tema")
            or "Empresa"
        )
        subject = strip_html_to_plain_line(subject, max_len=255) or "Empresa"
        corp_flags = corporate_dossier_module_flags(depth_key)
        dossier = Dossier(
            id=dossier_id,
            organization_id=org_id,
            requested_by_user_id=user_id,
            contact_id=None,
            subject_name=subject,
            subject_email=None,
            module_identity=corp_flags["module_identity"],
            module_corporate=corp_flags["module_corporate"],
            module_media=corp_flags["module_media"],
            depth_level=depth_key,
            credits_consumed=corp_cost if will_charge_corp else 0,
            status=status,
            status_message="Error en el informe generado." if is_err else None,
            dossier_data={
                "format": "markdown",
                "body": corporate_md,
                "pipeline": "langgraph_corporate",
                "success": not is_err,
                "billing": "charged" if will_charge_corp else "none",
                "cache": {
                    "hit": corporate_cache_hit,
                    "redis": redis_corporate_cache_available(),
                },
                "calendar": cal,
                "calendar_folder": calendar_folder,
                "calendar_folder_role": "corporate",
                "output_language": output_lang,
                **_progress_copy(corporate_progress),
            },
            agents_activated=["agent_corporate_uk", "agent_corporate_usa", "synthesize_llm"],
            agents_failed=corp_agents_failed,
            data_sources_used=["companies_house", "sec_edgar", "sec_company_facts", "gemini"],
            generation_started_at=now,
            generation_completed_at=now,
            generation_duration_ms=0 if corporate_cache_hit else generation_duration_ms,
            cache_key=result.get("corporate_cache_key") if corporate_cache_hit else None,
            cached_until=cache_expires if corporate_cache_hit else None,
            trigger_source=trigger_source,
            calendar_event_id=calendar_event_id,
            dossier_folder_id=folder_id,
        )
        db.add(dossier)
        saved["corporate"] = {
            "id": str(dossier_id),
            "status": status,
            "subject_name": subject,
        }
        saved["folder"] = {"id": str(folder_id), "title": folder_title}

    person_md = result.get("dossier_persona")
    person_payload = result.get("dossier_persona_research")
    dossier_personas = result.get("dossier_personas")
    if not dossier_personas:
        person_name = (parsed.get("person_name") or "").strip()
        if len(person_name) >= 2:
            dossier_personas = [
                {
                    "full_name": person_name,
                    "job_area": parsed.get("person_job"),
                    "country": parsed.get("person_country"),
                    "email": parsed.get("person_email"),
                    "md": person_md,
                    "payload": person_payload,
                    "cache_hit": person_cache_hit,
                    "cache_key": result.get("person_cache_key"),
                }
            ]
    else:
        dossier_personas = list(dossier_personas)

    saved["persons"] = []
    for pentry in dossier_personas or []:
        person_name = (pentry.get("full_name") or "").strip()
        if len(person_name) < 2:
            continue

        p_md = pentry.get("md")
        p_payload = pentry.get("payload")
        p_cache_hit = bool(pentry.get("cache_hit"))
        p_cache_key = pentry.get("cache_key")

        valid_person_md = normalize_person_report_text(p_md)
        if valid_person_md:
            status = "complete"
            status_message = None
            body = valid_person_md
            success = True
        else:
            status = "failed"
            status_message = _person_failure_message(
                person_payload=p_payload if isinstance(p_payload, dict) else None,
                errors=result.get("errors"),
                person_md=p_md if isinstance(p_md, str) else None,
            )
            body = ""
            success = False

        will_charge_person = charge and status == "complete" and not p_cache_hit
        sid = pentry.get("scope_id")
        person_progress = job_progress.scope(sid) if sid else NULL_SCOPE
        person_progress.stage(PERSIST, "running")
        lusha_diag: dict[str, Any] | None = None
        person_research_source = "pdl"
        if isinstance(p_payload, dict):
            fa = p_payload.get("filters_applied")
            if isinstance(fa, dict) and fa.get("research_source"):
                person_research_source = str(fa["research_source"])
            lusha_diag = {
                "profiles_count": profiles_count_from_research_result(p_payload),
                "profile_urls": p_payload.get("profile_urls") or [],
                "warnings": p_payload.get("warnings") or [],
                "gemini_google_search_used": p_payload.get("gemini_google_search_used"),
                "filters_applied": p_payload.get("filters_applied"),
            }
        # Sin respaldo en ``parsed["person_email"]``: es el del primer contacto, no el de este.
        person_email_stored = (pentry.get("email") or "")[:255] or None
        dossier_id = uuid.uuid4()
        dossier = Dossier(
            id=dossier_id,
            organization_id=org_id,
            requested_by_user_id=user_id,
            contact_id=None,
            subject_name=person_name[:255],
            subject_email=person_email_stored,
            module_identity=True,
            module_corporate=False,
            module_media=False,
            depth_level="basic",
            credits_consumed=person_cost if will_charge_person else 0,
            status=status,
            status_message=status_message,
            dossier_data={
                "format": "markdown",
                "body": body,
                "pipeline": "person_research",
                "success": success,
                "billing": "charged" if will_charge_person else "none",
                "cache": {
                    "hit": p_cache_hit,
                    "redis": redis_person_cache_available(),
                },
                "calendar": cal,
                "calendar_folder": calendar_folder,
                "calendar_folder_role": "person",
                "person_filters": {
                    "full_name": person_name,
                    "job_area": pentry.get("job_area"),
                    "company": parsed.get("company_person"),
                    "country": pentry.get("country"),
                    "email": pentry.get("email") or None,
                    "research_source": person_research_source,
                    "contact_index": pentry.get("index"),
                },
                "lusha_diagnostics": lusha_diag,
                "output_language": output_lang,
                **_progress_copy(person_progress),
            },
            agents_activated=[],
            agents_failed=(["deepseek_person_analysis"] if status == "failed" else []),
            data_sources_used=[person_research_source, "deepseek"],
            generation_started_at=now,
            generation_completed_at=now,
            generation_duration_ms=0 if p_cache_hit else generation_duration_ms,
            cache_key=p_cache_key if p_cache_hit else None,
            cached_until=cache_expires if p_cache_hit else None,
            trigger_source=trigger_source,
            calendar_event_id=calendar_event_id,
            dossier_folder_id=folder_id,
        )
        db.add(dossier)
        person_ref = {
            "id": str(dossier_id),
            "status": status,
            "subject_name": person_name[:255],
            "status_message": status_message,
            "cache_hit": p_cache_hit,
        }
        saved["persons"].append(person_ref)
        guardados_persona.append((person_progress, str(dossier_id), status))
        if "person" not in saved:
            saved["person"] = person_ref
        if "folder" not in saved:
            saved["folder"] = {"id": str(folder_id), "title": folder_title}

    if saved:
        try:
            db.commit()
        except Exception:
            for person_progress, _, _ in guardados_persona:
                person_progress.stage(PERSIST, "failed", "persistence_error")
            raise
        SUMMARY_CACHE.invalidate(user_id)  # los indicadores de Resumen cambian con cada resultado
        if "corporate" in saved:
            corporate_progress.fields(dossier={"id": saved["corporate"]["id"], "status": saved["corporate"]["status"]})
        for person_progress, guardado_id, guardado_status in guardados_persona:
            report_persisted(person_progress, dossier_id=guardado_id, dossier_status=guardado_status)

    result["saved_dossiers"] = saved
    return result


def _progress_copy(progress: Any) -> dict[str, Any]:
    """``{"_progress": …}`` para ``dossier_data``, o nada si no hay job (ADR 0009)."""
    copia = scope_copy(progress)
    return {"_progress": copia} if copia else {}
