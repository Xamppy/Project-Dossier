"""Variantes de nombre de empresa para búsqueda PDL y contexto de persona."""
from __future__ import annotations

import re
import unicodedata

_PARENS_ACRONYM = re.compile(r"\(([^)]+)\)")
_CORP_SUFFIX = re.compile(
    r"\s+(?:CORP\.?|INC\.?|LTD\.?|LLC\.?|S\.A\.?|SA\.?|LIMITED|PLC)\.?\s*$",
    re.IGNORECASE,
)
PERSONAL_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "yahoo.com",
        "icloud.com",
        "me.com",
        "proton.me",
        "protonmail.com",
    }
)

_KNOWN_COMPANY_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)universidad\s+tecnol[oó]gica\s+metropolitana"), "UTEM"),
    (re.compile(r"(?i)universidad\s+de\s+chile"), "UCHILE"),
    (re.compile(r"(?i)pontificia\s+universidad\s+cat[oó]lica\s+de\s+chile"), "PUC"),
)


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def email_to_company_domain(email: str | None) -> str | None:
    """Dominio corporativo desde email (p. ej. nombre@utem.cl → utem.cl)."""
    if not email or "@" not in email:
        return None
    domain = email.split("@", 1)[1].strip().lower()
    if not domain or domain in PERSONAL_EMAIL_DOMAINS:
        return None
    return domain


def company_search_variants(company: str | None) -> list[str]:
    """
    Genera alias de empresa para búsquedas PDL.

    - Texto entre paréntesis: «Universidad X (UTEM)» → UTEM
    - Sin sufijos legales: «Nvidia CORP» → Nvidia
    - Sin tildes + alias conocidos (p. ej. UTEM)
    """
    if not company or not str(company).strip():
        return []

    raw = str(company).strip()
    variants: list[str] = [raw]

    m = _PARENS_ACRONYM.search(raw)
    if m:
        inner = m.group(1).strip()
        if 2 <= len(inner) <= 20:
            variants.append(inner)
        without = _PARENS_ACRONYM.sub("", raw).strip(" ,-–—")
        if without and without != raw:
            variants.append(without)

    for v in list(variants):
        stripped = _CORP_SUFFIX.sub("", v).strip()
        if stripped and stripped != v:
            variants.append(stripped)

    for v in list(variants):
        plain = strip_accents(v)
        if plain != v:
            variants.append(plain)

    for pattern, alias in _KNOWN_COMPANY_ALIASES:
        if any(pattern.search(v) for v in variants):
            variants.append(alias)

    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        key = v.lower()
        if len(v) >= 2 and key not in seen:
            seen.add(key)
            out.append(v)
    return out
