"""Idioma de salida de dossiers (configuración UI → prompts LLM)."""
from __future__ import annotations

import re

# Códigos normalizados que el pipeline entiende.
SUPPORTED_OUTPUT_CODES = frozenset({"es", "en", "pt", "it", "fr", "de"})

_LANGUAGE_LABELS: dict[str, str] = {
    "es": "español",
    "en": "inglés",
    "pt": "portugués",
    "it": "italiano",
    "fr": "francés",
    "de": "alemán",
}

# Instrucciones en el idioma objetivo (más fiables que solo decir «francés» en español).
_DOSSIER_LANGUAGE_BLOCKS: dict[str, str] = {
    "en": (
        "**Mandatory output language:** Write the **entire** executive dossier in **English** "
        "(section titles, tables, bullet points, risk levels, and recommendations). "
        "Do **not** leave Spanish headings from the template (e.g. translate "
        "«FICHA DE IDENTIDAD» → «IDENTITY CARD», «RESUMEN EJECUTIVO» → «EXECUTIVE SUMMARY»). "
        "Keep bracket tags in English where applicable: [INFERENCE], [OBSERVATION], "
        "[INCONSISTENCY], [LOW ALERT], [MODERATE ALERT], [CRITICAL ALERT]. "
        "Maintain a formal executive tone. **Do not mix languages.**"
    ),
    "pt": (
        "**Idioma de saída obrigatório:** redija **todo** o dossiê executivo em **português** "
        "(títulos de seção, tabelas, marcadores, níveis de risco, recomendações e texto corrido). "
        "Não deixe títulos em espanhol ou inglês (ex.: «RESUMEN EJECUTIVO» → «RESUMO EXECUTIVO»). "
        "Nomes próprios, tickers e bolsas podem permanecer como estão. "
        "Use etiquetas entre colchetes em português: [INFERÊNCIA], "
        "[OBSERVAÇÃO], [INCONSISTÊNCIA], [ALERTA LEVE], [ALERTA MODERADA], [ALERTA CRÍTICA]. "
        "Tom formal e executivo. **Não misture idiomas.**"
    ),
    "it": (
        "**Lingua di output obbligatoria:** redigi **l'intero** dossier esecutivo in **italiano** "
        "(titoli di sezione, tabelle, elenchi, livelli di rischio, raccomandazioni e testo). "
        "Non lasciare titoli in spagnolo o inglese (es. «RESUMEN EJECUTIVO» → «SOMMARIO ESECUTIVO»). "
        "Nomi propri, ticker e borse possono restare invariati. "
        "Usa tag tra parentesi quadre in italiano: [INFERENZA], [OSSERVAZIONE], "
        "[INCOERENZA], [ALLERTA LIEVE], [ALLERTA MODERATA], [ALLERTA CRITICA]. "
        "Tono formale ed esecutivo. **Non mescolare lingue.**"
    ),
    "fr": (
        "**Langue de sortie obligatoire :** rédigez **l'intégralité** du dossier en **français** "
        "(titres de section, tableaux, puces, niveaux de risque, recommandations et prose). "
        "Ne conservez pas de titres en espagnol ou en anglais (ex. « RESUMEN EJECUTIVO » → « RÉSUMÉ EXÉCUTIF »). "
        "Noms propres, tickers et places boursières peuvent rester tels quels. "
        "Utilisez des balises entre crochets en français : [INFÉRENCE], [OBSERVATION], "
        "[INCOHÉRENCE], [ALERTE LÉGÈRE], [ALERTE MODÉRÉE], [ALERTE CRITIQUE]. "
        "Ton formel et exécutif. **Ne mélangez pas les langues.**"
    ),
    "de": (
        "**Ausgabesprache (Pflicht):** Verfassen Sie den **gesamten** Bericht auf **Deutsch** "
        "(Abschnittstitel, **Feldbezeichnungen**, Tabellen, Aufzählungen, Risikoniveaus, Empfehlungen und Fließtext). "
        "Keine spanischen oder englischen Überschriften oder Formulierungen (z. B. «Nombre completo» → "
        "«Vollständiger Name», «Lista cronológica inversa» → «Umgekehrte chronologische Liste»). "
        "Eigennamen, Tickers und Börsenplätze dürfen unübersetzt bleiben. "
        "Verwenden Sie Klammer-Tags auf Deutsch: [INFERENZ], [BEOBACHTUNG], "
        "[INKONSISTENZ], [LEICHTE WARNUNG], [MODERATE WARNUNG], [KRITISCHE WARNUNG]. "
        "Formeller, sachlicher Executive-Ton. **Keine Sprachmischung.**"
    ),
}


def normalize_output_language(raw: str | None) -> str:
    """Normaliza locale/código de salida; por defecto español."""
    if not raw or not str(raw).strip():
        return "es"
    code = str(raw).strip().lower().replace("_", "-")
    if code.startswith("en"):
        return "en"
    if code.startswith("es"):
        return "es"
    if code.startswith("pt"):
        return "pt"
    if code.startswith("it"):
        return "it"
    if code.startswith("fr"):
        return "fr"
    if code.startswith("de"):
        return "de"
    return "es"


def resolve_output_language_from_user_locale(user_locale: str | None) -> str:
    """Fallback servidor (calendario/automatización): locale de cuenta en PostgreSQL."""
    return normalize_output_language(user_locale)


def resolve_dossier_output_language(
    ui_locale: str | None,
    dossier_output_pref: str | None,
) -> str:
    """
    Misma lógica que ``resolveDossierOutputLanguage`` en el frontend.

    - ``match``: idioma de la interfaz (``ui_locale``).
    - ``auto``: español (legado).
    - ``es`` | ``en`` | …: idioma fijo del dossier.
    """
    pref = (dossier_output_pref or "match").strip().lower()
    if pref == "auto":
        return "es"
    if pref == "match":
        return normalize_output_language(ui_locale)
    return normalize_output_language(pref)


def resolve_dossier_output_language_for_user(user) -> str:
    """Idioma efectivo de dossier para un usuario (automatización / fallback API)."""
    locale = getattr(user, "locale", None)
    pref = getattr(user, "dossier_output_language", None) or "match"
    return resolve_dossier_output_language(locale, pref)


def effective_output_language(user, explicit: str | None = None) -> str:
    """Prioridad: parámetro explícito de la petición → preferencias guardadas del usuario."""
    if explicit is not None and str(explicit).strip():
        raw = str(explicit).strip().lower()
        if raw in ("match", "auto"):
            if user is None:
                return "es"
            return resolve_dossier_output_language_for_user(user)
        return normalize_output_language(explicit)
    if user is None:
        return "es"
    return resolve_dossier_output_language_for_user(user)


def dossier_language_instruction(code: str) -> str:
    """Bloque corto para anexar a prompts de sistema."""
    normalized = normalize_output_language(code)
    if normalized == "es":
        return ""
    block = _DOSSIER_LANGUAGE_BLOCKS.get(normalized)
    if block:
        return f"\n\n{block}"
    lang = _LANGUAGE_LABELS.get(normalized, "español")
    return (
        f"\n\n**Idioma de salida obligatorio:** redacta **todo** el informe en **{lang}** "
        f"(incluidos títulos de sección, tablas y viñetas). Mantén el tono ejecutivo."
    )


def apply_output_language_to_system_prompt(system: str, code: str) -> str:
    """Ajusta prompts que asumen español (corporativo y persona)."""
    from dossier.services.dossier_prompt_locales import system_writing_line

    normalized = normalize_output_language(code)
    if normalized == "es":
        return system
    lang = _LANGUAGE_LABELS[normalized]
    updated = system
    write_line = system_writing_line(normalized)
    if write_line:
        updated = re.sub(
            r"Redactas en español,\s*en Markdown\.?",
            write_line,
            updated,
            count=1,
            flags=re.IGNORECASE,
        )
    for pattern, repl in (
        (r"- Redacta en \*\*español\*\*\.?", f"- Redacta en **{lang}**."),
        (r"Redacta en \*\*español\*\*\.?", f"Redacta en **{lang}**."),
        (
            r"- Redacta en el idioma indicado por la configuración de salida del dossier[^\n]*",
            f"- {write_line or f'Redacta en **{lang}**.'}",
        ),
        (
            r"- Si el idioma no es español, \*\*traduce\*\* todos los títulos de sección[^\n]*",
            "- Usa **solo** los títulos de sección del idioma objetivo; no mezcles idiomas.",
        ),
    ):
        updated = re.sub(pattern, repl, updated, count=1, flags=re.IGNORECASE)
    block = dossier_language_instruction(normalized)
    if block and block not in updated:
        updated = updated + block
    return updated
