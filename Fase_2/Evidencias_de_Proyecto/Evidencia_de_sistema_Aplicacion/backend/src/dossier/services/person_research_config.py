"""Fuente por defecto para investigación de persona (calendario y API)."""
from __future__ import annotations

import os

from dossier.schemas.person_research import PersonResearchSource


def default_person_research_source() -> PersonResearchSource:
    raw = (os.getenv("PERSON_RESEARCH_PROVIDER") or "pdl").strip().lower()
    if raw in ("gemini_web", "gemini", "deepseek_web", "web"):
        return PersonResearchSource.gemini_web
    return PersonResearchSource.pdl
