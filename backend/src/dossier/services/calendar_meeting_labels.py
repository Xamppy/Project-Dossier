"""Etiquetas de campos en eventos de calendario (es, en, pt, it, fr, de)."""
from __future__ import annotations

import re

# Idiomas de interfaz / salida de dossiers de la plataforma.
COMPANY_LABELS: tuple[str, ...] = (
    "empresa",
    "company",
    "compañía",
    "compania",
    "compañia",
    "cliente",
    "client",
    "organización",
    "organizacion",
    "organization",
    "organização",
    "organizacao",
    "entreprise",
    "société",
    "societe",
    "azienda",
    "impresa",
    "società",
    "societa",
    "unternehmen",
    "firma",
    "kunde",
)

PERSON_LABELS: tuple[str, ...] = (
    "contacto",
    "contact",
    "nombre",
    "name",
    "nome",
    "nom",
    "contatto",
    "kontakt",
    # Plurales y portugués («Contactos:», «Contato 1:»); BUG-2026-10-19-04.
    "contactos",
    "contacts",
    "contato",
    "contatos",
    "contatti",
    "kontakte",
)

JOB_LABELS: tuple[str, ...] = (
    "cargo",
    "puesto",
    "rol",
    "role",
    "rolle",
    "título",
    "titulo",
    "title",
    "job",
    "position",
    "poste",
    "fonction",
    "ruolo",
    "carica",
    "posizione",
    "função",
    "funcao",
    "papel",
    "stelle",
    "bereich",
    "área",
    "area",
)

COUNTRY_LABELS: tuple[str, ...] = (
    "país",
    "pais",
    "country",
    "pays",
    "paese",
    "land",
)

EMAIL_LABELS: tuple[str, ...] = (
    "email",
    "e-mail",
    "correo",
    "correio",
    "mail",
    "courriel",
)

MEETING_WITH_SUBJECT_PHRASES: tuple[str, ...] = (
    "reunión con",
    "reunion con",
    "meeting with",
    "reunião com",
    "reuniao com",
    "riunione con",
    "incontro con",
    "réunion avec",
    "reunion avec",
    "rendez-vous avec",
    "meeting mit",
    "besprechung mit",
    "termin mit",
)

# Todas las etiquetas estructuradas (para cortar valores en la misma línea).
ALL_STRUCTURED_FIELD_LABELS: tuple[str, ...] = (
    *COMPANY_LABELS,
    *PERSON_LABELS,
    *JOB_LABELS,
    *COUNTRY_LABELS,
    *EMAIL_LABELS,
)


def _alt(*terms: str) -> str:
    unique: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(re.escape(term))
    return "|".join(unique)


# Una etiqueta solo cuenta como palabra completa (BUG-2026-10-19-05): no puede ir pegada a una
# letra, un dígito, «_», «@», «.» ni «-». Así «mail» no es etiqueta dentro de «gmail.com»,
# «ana@mail.com» ni «e-mail» (que ya es etiqueta por sí misma), y «nome» no lo es en «genome».
# El frontend replica esta regla en `frontend/src/lib/calendar-meeting-format.ts`.
_LABEL_START = r"(?<![\w@.\-])"

# El punto como separador («Email. ana@x») exige espacio o fin detrás; si no, «nombre.apellido@»
# o «correo.ana@» dentro de una dirección parecerían un campo nuevo.
_DOT_SEPARATOR = r"\.(?=\s|\Z)"


def _labels(*terms: str) -> str:
    """Alternativa de etiquetas anclada a inicio de palabra."""
    return rf"{_LABEL_START}(?:{_alt(*terms)})"


def _field_value_boundary() -> str:
    """
    Fin del valor de un campo: salto de línea u otra etiqueta conocida.

    Outlook/Google a veces dejan «Azienda: X Contatto: Y» en una sola línea;
    sin esto la empresa captura también el contacto.
    """
    labels = _labels(*ALL_STRUCTURED_FIELD_LABELS)
    return rf"(?=\s*(?:\n|{labels}\s*(?:\d+\s*)?(?::|{_DOT_SEPARATOR})|\Z))"


def labeled_field_pattern(labels: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        rf"(?i){_labels(*labels)}\s*:\s*(.+?){_field_value_boundary()}"
    )


def numbered_field_pattern(labels: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        rf"(?i){_labels(*labels)}\s*(\d+)\s*:\s*(.+?){_field_value_boundary()}"
    )


# Guion como separador de un campo persona («Contacto 2 - Ana»): solo a inicio de línea y con
# espacio detrás, para no confundirlo con un guion dentro de una frase («genome - análisis»).
# El frontend replica esta regla en `frontend/src/lib/calendar-meeting-format.ts`.
_LINE_START = r"(?<![^\n])[ \t]*"
_DASH_SEPARATOR = r"[ \t]*[-–—][ \t]+"


def person_dash_field_pattern() -> re.Pattern[str]:
    """«Contacto - Ana» a inicio de línea; el valor empieza por un carácter visible."""
    return re.compile(
        rf"(?i){_LINE_START}(?:{_alt(*PERSON_LABELS)}){_DASH_SEPARATOR}(\S.*?){_field_value_boundary()}"
    )


def numbered_person_dash_field_pattern() -> re.Pattern[str]:
    """«Contacto 2 - Ana» a inicio de línea; grupos: (número, valor) como `numbered_field_pattern`."""
    return re.compile(
        rf"(?i){_LINE_START}(?:{_alt(*PERSON_LABELS)})[ \t]*(\d+){_DASH_SEPARATOR}(\S.*?)"
        rf"{_field_value_boundary()}"
    )


def country_field_pattern() -> re.Pattern[str]:
    return re.compile(
        rf"(?i){_labels(*COUNTRY_LABELS)}(?:\s*\([^)]*\))?\s*:\s*(.+?){_field_value_boundary()}"
    )


def numbered_country_field_pattern() -> re.Pattern[str]:
    return re.compile(
        rf"(?i){_labels(*COUNTRY_LABELS)}(?:\s*\([^)]*\))?\s*(\d+)\s*:\s*(.+?){_field_value_boundary()}"
    )


def email_field_pattern() -> re.Pattern[str]:
    return re.compile(
        rf"(?i){_labels(*EMAIL_LABELS)}\s*(?::|{_DOT_SEPARATOR})\s*(.+?){_field_value_boundary()}"
    )


def numbered_email_field_pattern() -> re.Pattern[str]:
    return re.compile(
        rf"(?i){_labels(*EMAIL_LABELS)}\s*(\d+)\s*(?::|{_DOT_SEPARATOR})\s*(.+?){_field_value_boundary()}"
    )


def country_inline_in_job_pattern() -> re.Pattern[str]:
    return re.compile(rf"(?i)\s+(?:{_alt(*COUNTRY_LABELS)})\s*:\s*(.+)$")


def subject_meeting_with_pattern() -> re.Pattern[str]:
    phrases = "|".join(re.escape(p) for p in MEETING_WITH_SUBJECT_PHRASES)
    return re.compile(rf"(?i)^(?:{phrases})\s+(.+)$")


def person_hint_patterns() -> tuple[re.Pattern[str], ...]:
    return (
        labeled_field_pattern(PERSON_LABELS),
        person_dash_field_pattern(),
        *(
            re.compile(rf"(?i){re.escape(phrase)}\s+(.+?)(?:\n|$)")
            for phrase in MEETING_WITH_SUBJECT_PHRASES
        ),
    )


def numbered_person_patterns() -> tuple[re.Pattern[str], ...]:
    """Contactos numerados: «Contacto 1: Ana» en cualquier parte, «Contacto 2 - Luis» a inicio de línea."""
    return (numbered_field_pattern(PERSON_LABELS), numbered_person_dash_field_pattern())


def _person_label_source() -> str:
    """Etiqueta persona declarada: «Contacto:», «Contacto 1:» o «Contacto 2 - » a inicio de línea."""
    labels = _alt(*PERSON_LABELS)
    colon = rf"{_LABEL_START}(?:{labels})\s*(?:\d+\s*)?:"
    dash = rf"{_LINE_START}(?:{labels})[ \t]*(?:\d+[ \t]*)?[-–—](?=[ \t])"
    return rf"(?:{colon}|{dash})"


def business_signal_patterns() -> tuple[re.Pattern[str], ...]:
    return (
        re.compile(rf"(?i){_labels(*COMPANY_LABELS)}\s*:"),
        re.compile(rf"(?i){_person_label_source()}"),
    )


def person_hint_regex_source() -> str:
    """
    Regla de «hay contacto en la descripción»: etiqueta persona seguida de un valor visible.

    Es la fuente de verdad del aviso «No se detecta contacto» del frontend
    (`descriptionHasPersonHint` en `frontend/src/lib/calendar-meeting-format.ts`).
    """
    labels = _alt(*PERSON_LABELS)
    colon = rf"{_LABEL_START}(?:{labels})\s*(?:\d+\s*)?:\s*\S"
    dash = rf"{_LINE_START}(?:{labels})[ \t]*(?:\d+[ \t]*)?[-–—][ \t]+\S"
    phrases = "|".join(re.escape(p) for p in MEETING_WITH_SUBJECT_PHRASES)
    return rf"(?:{colon}|{dash}|(?:{phrases})\s+\S)"


# Patrones compilados (uso en calendar_event_dossiers / filters).
EMPRESA_DESC = labeled_field_pattern(COMPANY_LABELS)
PERSON_PATTERNS = person_hint_patterns()
EMAIL_IN_DESC = email_field_pattern()
JOB_IN_DESC = labeled_field_pattern(JOB_LABELS)
COUNTRY_IN_DESC = country_field_pattern()
NUMBERED_CONTACT_PATTERNS = numbered_person_patterns()
NUMBERED_JOB = numbered_field_pattern(JOB_LABELS)
NUMBERED_EMAIL = numbered_email_field_pattern()
NUMBERED_COUNTRY = numbered_country_field_pattern()
SUBJECT_CON = subject_meeting_with_pattern()
COUNTRY_INLINE_IN_JOB = country_inline_in_job_pattern()
