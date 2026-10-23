"""Extracción de hechos estructurados desde perfiles de enriquecimiento (PDL)."""
from __future__ import annotations

from typing import Any


def _first_str(*values: Any) -> str | None:
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _emails_from_data(data: dict[str, Any]) -> list[str]:
    out: list[str] = []
    emails = data.get("emails")
    if isinstance(emails, list):
        for item in emails:
            if isinstance(item, dict):
                em = _first_str(item.get("email"), item.get("address"))
                if em:
                    out.append(em)
            elif isinstance(item, str) and "@" in item:
                out.append(item.strip())
    single = data.get("email")
    if isinstance(single, str) and "@" in single:
        out.append(single.strip())
    work = data.get("work_email")
    if isinstance(work, str) and "@" in work:
        out.append(work.strip())
    seen: set[str] = set()
    unique: list[str] = []
    for em in out:
        low = em.lower()
        if low not in seen:
            seen.add(low)
            unique.append(em)
    return unique


def _phones_from_data(data: dict[str, Any]) -> list[str]:
    out: list[str] = []
    phones = data.get("phones")
    if isinstance(phones, list):
        for item in phones:
            if isinstance(item, dict):
                ph = _first_str(item.get("number"), item.get("phone"), item.get("internationalNumber"))
                if ph:
                    out.append(ph)
            elif isinstance(item, str) and item.strip():
                out.append(item.strip())
    for key in ("phone_numbers",):
        pn = data.get(key)
        if isinstance(pn, list):
            for item in pn:
                if isinstance(item, dict):
                    ph = _first_str(item.get("number"), item.get("sanitized_number"))
                    if ph:
                        out.append(ph)
                elif isinstance(item, str) and item.strip():
                    out.append(item.strip())
    return out


def _linkedin_from_data(data: dict[str, Any]) -> str | None:
    direct = _first_str(data.get("linkedin_url"), data.get("linkedinUrl"))
    if direct:
        return direct
    social = data.get("socialLinks")
    if isinstance(social, dict):
        url = _first_str(social.get("linkedin"), social.get("linkedIn"))
        if url:
            return url
    return None


def _job_title_from_data(data: dict[str, Any]) -> str | None:
    jt = data.get("jobTitle")
    if isinstance(jt, dict):
        return _first_str(jt.get("title"), jt.get("name"))
    return _first_str(jt, data.get("title"), data.get("currentTitle"), data.get("job_title"))


def _company_from_data(data: dict[str, Any]) -> str | None:
    comp = data.get("company")
    if isinstance(comp, dict):
        return _first_str(comp.get("name"), comp.get("companyName"))
    return _first_str(
        comp,
        data.get("companyName"),
        data.get("currentCompanyName"),
        data.get("job_company_name"),
    )


def _location_from_data(data: dict[str, Any]) -> str | None:
    loc = data.get("location")
    if isinstance(loc, dict):
        city = _first_str(loc.get("city"))
        country = _first_str(loc.get("country"))
        if city and country:
            return f"{city}, {country}"
        return city or country
    loc_name = _first_str(data.get("location_name"))
    if loc_name:
        return loc_name
    city = _first_str(data.get("location_locality"), data.get("locality"))
    country = _first_str(data.get("location_country"), data.get("country"))
    if city and country:
        return f"{city}, {country}"
    return city or country or _first_str(loc)


def extract_facts_from_lusha_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Hechos verificables de un perfil Lusha (preview o enriquecido)."""
    data = profile.get("data") if isinstance(profile.get("data"), dict) else profile
    if not isinstance(data, dict):
        return {}

    first = _first_str(data.get("firstName"), data.get("first_name"))
    last = _first_str(data.get("lastName"), data.get("last_name"))
    full = _first_str(data.get("full_name"), data.get("fullName"), data.get("name"))
    if not full and first:
        full = f"{first} {last or ''}".strip()

    linkedin = _linkedin_from_data(data)
    urls = profile.get("linkedin_urls")
    if not linkedin and isinstance(urls, list) and urls:
        linkedin = _first_str(urls[0])

    return {
        "provider": profile.get("provider") or "lusha",
        "lusha_id": profile.get("lusha_id") or profile.get("pdl_id") or _first_str(data.get("id")),
        "full_name": full,
        "job_title": _job_title_from_data(data),
        "company": _company_from_data(data),
        "location": _location_from_data(data),
        "linkedin_url": linkedin,
        "emails": _emails_from_data(data),
        "phones": _phones_from_data(data),
    }


def merge_lusha_profiles_facts(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """Fusiona hechos del primer perfil con datos más completos."""
    merged: dict[str, Any] = {
        "profiles_matched": len(profiles),
        "linkedin_url": None,
        "emails": [],
        "phones": [],
        "job_title": None,
        "company": None,
        "location": None,
        "full_name": None,
    }
    all_emails: list[str] = []
    all_phones: list[str] = []

    for p in profiles:
        facts = extract_facts_from_lusha_profile(p)
        if not merged["full_name"] and facts.get("full_name"):
            merged["full_name"] = facts["full_name"]
        if not merged["job_title"] and facts.get("job_title"):
            merged["job_title"] = facts["job_title"]
        if not merged["company"] and facts.get("company"):
            merged["company"] = facts["company"]
        if not merged["location"] and facts.get("location"):
            merged["location"] = facts["location"]
        if not merged["linkedin_url"] and facts.get("linkedin_url"):
            merged["linkedin_url"] = facts["linkedin_url"]
        for em in facts.get("emails") or []:
            if em not in all_emails:
                all_emails.append(em)
        for ph in facts.get("phones") or []:
            if ph not in all_phones:
                all_phones.append(ph)

    merged["emails"] = all_emails
    merged["phones"] = all_phones
    return merged


def format_lusha_verified_facts_block(
    facts: dict[str, Any],
    *,
    provider: str | None = None,
    output_language: str = "es",
) -> str:
    """Bloque obligatorio para el prompt cuando Lusha devolvió datos."""
    if not facts or facts.get("profiles_matched", 0) == 0:
        return ""

    from dossier.services.person_dossier_locales import (
        verified_facts_field_labels,
        verified_facts_heading,
    )

    label = (provider or facts.get("provider") or "LUSHA").upper()
    fields = verified_facts_field_labels(output_language)
    lines = [verified_facts_heading(output_language, label)]
    if facts.get("full_name"):
        lines.append(f"- {fields['name']}: {facts['full_name']}")
    if facts.get("job_title"):
        lines.append(f"- {fields['job']}: {facts['job_title']}")
    if facts.get("company"):
        lines.append(f"- {fields['company']}: {facts['company']}")
    if facts.get("location"):
        lines.append(f"- {fields['location']}: {facts['location']}")
    if facts.get("linkedin_url"):
        lines.append(f"- {fields['linkedin']}: {facts['linkedin_url']}")
    for em in facts.get("emails") or []:
        lines.append(f"- {fields['email']}: {em}")
    for ph in facts.get("phones") or []:
        lines.append(f"- {fields['phone']}: {ph}")
    if len(lines) <= 1:
        return ""
    return "\n".join(lines) + "\n\n"
