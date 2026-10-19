"""Parseo de etiquetas de calendario en varios idiomas."""

import re
from pathlib import Path

import pytest

from dossier.services.calendar_event_dossiers import (
    extract_all_persons_from_description,
    extract_company_from_description,
    extract_email_from_description,
    extract_numbered_persons_from_description,
    extract_person_from_description,
    parse_calendar_event_for_dossiers,
)
from dossier.services.calendar_event_filters import has_business_meeting_signals
from dossier.services.calendar_meeting_labels import PERSON_LABELS, person_hint_regex_source

_FRONTEND_LABELS = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "calendar-meeting-format.ts"
)


def test_italian_labels_same_line():
    desc = "Azienda: NoonDalton Contatto: Edward Dalton"
    assert extract_company_from_description(desc) == "NoonDalton"
    assert extract_person_from_description(desc)[0] == "Edward Dalton"


def test_italian_labels_multiline():
    desc = "Azienda: NoonDalton\nContatto: Edward Dalton"
    assert extract_company_from_description(desc) == "NoonDalton"
    assert extract_person_from_description(desc)[0] == "Edward Dalton"


def test_spanish_labels_same_line():
    desc = "Empresa: Acme Corp Contacto: Ana García"
    assert extract_company_from_description(desc) == "Acme Corp"
    assert extract_person_from_description(desc)[0] == "Ana García"


def test_business_signals_detect_italian():
    reunion = {
        "tema": "Reunion NoonDalton",
        "descripcion": "Azienda: NoonDalton Contatto: Edward Dalton",
    }
    assert has_business_meeting_signals(reunion) is True
    parsed = parse_calendar_event_for_dossiers(reunion)
    assert parsed["company_corporate"] == "NoonDalton"
    assert parsed["person_name"] == "Edward Dalton"


# --- BUG-2026-10-19-04: variantes numeradas, plurales y con guion -------------------------


@pytest.mark.parametrize(
    ("desc", "nombre"),
    [
        ("Empresa: Acme\nContacto 1: Ana Pérez <ana@acme.test>", "Ana Pérez"),
        ("Contact 1: John Smith", "John Smith"),
        ("Contato 1: João Silva", "João Silva"),
        ("Kontakt 1: Hans Müller", "Hans Müller"),
        ("Empresa: Acme\nContacto 2 - María López", "María López"),
        ("Empresa: Acme\n  Contacto 2 – María López", "María López"),
    ],
)
def test_numbered_contact_variants_are_extracted(desc, nombre):
    personas = extract_numbered_persons_from_description(desc)
    assert [p["full_name"] for p in personas] == [nombre]


def test_numbered_contacts_mix_colon_and_dash():
    desc = "Empresa: Acme\nContacto 1: Ana Pérez\nCargo 1: CEO\nContacto 2 - Luis Soto\nCargo 2: CTO"
    personas = extract_numbered_persons_from_description(desc)
    assert [(p["index"], p["full_name"], p["job_area"]) for p in personas] == [
        (1, "Ana Pérez", "CEO"),
        (2, "Luis Soto", "CTO"),
    ]


@pytest.mark.parametrize(
    ("desc", "nombre"),
    [
        ("Empresa: Acme\nContactos: Ana Pérez", "Ana Pérez"),
        ("Contacts: John Smith", "John Smith"),
        ("Empresa: Acme\nContato: João Silva", "João Silva"),
        ("Empresa: Acme\nContatos: João Silva", "João Silva"),
        ("Azienda: Acme\nContatti: Edward Dalton", "Edward Dalton"),
        ("Unternehmen: Acme\nKontakte: Hans Müller", "Hans Müller"),
        ("Empresa: Acme\nContacto - Ana Pérez", "Ana Pérez"),
    ],
)
def test_unnumbered_contact_variants_are_extracted(desc, nombre):
    assert extract_person_from_description(desc)[0] == nombre


def test_plural_label_cuts_company_on_same_line():
    assert extract_company_from_description("Empresa: Acme Corp Contatos: João Silva") == "Acme Corp"


@pytest.mark.parametrize(
    "desc",
    [
        "Empresa: Acme",
        "Empresa: Acme\nContacto 1:",
        "Empresa: Acme\nContacto 2 - ",
        "Empresa: Acme\nContacto 2 -María",
        "Empresa: Acme\nSecuenciación del genome - análisis",
        "Empresa: Acme\nPendiente de contacto con el cliente",
    ],
)
def test_no_contact_without_value_or_mid_sentence_dash(desc):
    assert extract_all_persons_from_description(desc) == []


@pytest.mark.parametrize(
    "desc",
    ["Contacto 1: Ana Pérez", "Contacto 2 - María López", "Contactos: Ana Pérez", "Contato: João"],
)
def test_business_signals_accept_contact_variants(desc):
    assert has_business_meeting_signals({"tema": "Revisión", "descripcion": desc}) is True


def test_business_signals_ignore_mid_sentence_dash():
    reunion = {"tema": "Revisión", "descripcion": "Secuenciación del genome - análisis"}
    assert has_business_meeting_signals(reunion) is False


def test_person_hint_regex_source_accepts_variants():
    rx = re.compile(person_hint_regex_source(), re.IGNORECASE)
    for desc in ("Contacto 1: Ana", "Contactos: Ana", "Contato: João", "Contacto 2 - Ana"):
        assert rx.search(desc), desc
    assert not rx.search("Secuenciación del genome - análisis")


def test_frontend_person_labels_match_backend():
    """El aviso del frontend usa la misma lista de etiquetas persona que el backend."""
    text = _FRONTEND_LABELS.read_text(encoding="utf-8")
    bloque = re.search(r"person:\s*\[(.*?)\]", text, flags=re.DOTALL)
    assert bloque, "No se encontró CALENDAR_FIELD_LABELS.person en el frontend"
    frontend = tuple(re.findall(r'"([^"]+)"', bloque.group(1)))
    assert frontend == PERSON_LABELS


# --- BUG-2026-10-19-05: una etiqueta solo cuenta como palabra completa ----------------------
# «mail» coincidía dentro de «gmail.» y cortaba el valor en «ana@g»; «nome» dentro de «genome».


@pytest.mark.parametrize(
    ("desc", "correo"),
    [
        ("Email: ana@gmail.com", "ana@gmail.com"),
        ("E-mail: ana@gmail.com", "ana@gmail.com"),
        ("Mail: ana@gmail.com", "ana@gmail.com"),
        ("Correo: ana@hotmail.com", "ana@hotmail.com"),
        ("Email: ana@mail.acme.test", "ana@mail.acme.test"),
        ("Email: nombre.apellido@acme.test", "nombre.apellido@acme.test"),
        ("Email. ana@gmail.com", "ana@gmail.com"),
    ],
)
def test_email_with_label_inside_domain_is_not_truncated(desc, correo):
    assert extract_email_from_description(desc) == correo


def test_numbered_email_with_gmail_is_not_truncated():
    desc = "Empresa: Acme\nContacto 1: Ana Gómez\nEmail 1: ana@gmail.com"
    personas = extract_numbered_persons_from_description(desc)
    assert [(p["full_name"], p["email"]) for p in personas] == [("Ana Gómez", "ana@gmail.com")]


@pytest.mark.parametrize(
    "desc",
    [
        "Empresa: Acme\nContacto 1: Ana <ana@gmail.com>",
        "Empresa: Acme\nContacto 1: Ana <ana@mail.acme.test>",
        "Empresa: Acme\nContacto 1: Ana <correo.ana@acme.test>",
        "Empresa: Acme\nContacto 1: Ana <nombre.ana@acme.test>",
    ],
)
def test_contact_name_is_not_cut_inside_the_email(desc):
    """Caso del hallazgo: el nombre queda sin el correo y el correo entero, nunca «Ana <ana@g»."""
    correo = desc.split("<", 1)[1].rstrip(">")
    personas = extract_numbered_persons_from_description(desc)
    assert [(p["full_name"], p["email"]) for p in personas] == [("Ana", correo)]


def test_contact_name_is_separated_from_angle_bracket_email():
    personas = extract_numbered_persons_from_description("Contacto 1: Ana <ana@gmail.com>")
    assert [(p["full_name"], p["email"]) for p in personas] == [("Ana", "ana@gmail.com")]


# Decisión de FO: «Nombre <correo>» se separa; un nombre con el correo pegado degrada la búsqueda
# en PDL. El correo entre <> solo se usa si no hay un «Email N:» / «Email:» explícito.


@pytest.mark.parametrize(
    ("desc", "esperado"),
    [
        ("Contacto 1: Ana Pérez <ana@acme.test>", [("Ana Pérez", "ana@acme.test")]),
        ("Contacto 1: Ana Pérez<ana@acme.test>", [("Ana Pérez", "ana@acme.test")]),
        ("Contacto 1: Ana Pérez <ANA@Acme.Test>", [("Ana Pérez", "ana@acme.test")]),
        ("Contacto 2 - Luis Soto <luis@acme.test>", [("Luis Soto", "luis@acme.test")]),
        (
            "Contacto 1: Ana Pérez <ana@acme.test>\nEmail 1: ana.perez@acme.test",
            [("Ana Pérez", "ana.perez@acme.test")],
        ),
        (
            "Contacto 1: Ana <ana@acme.test>\nContacto 2: Luis <luis@acme.test>",
            [("Ana", "ana@acme.test"), ("Luis", "luis@acme.test")],
        ),
        ("Contacto 1: Ana Pérez <sin correo>", [("Ana Pérez <sin correo>", None)]),
        ("Contacto 1: Ana Pérez", [("Ana Pérez", None)]),
    ],
)
def test_numbered_contact_angle_bracket_email_table(desc, esperado):
    personas = extract_numbered_persons_from_description(desc)
    assert [(p["full_name"], p["email"]) for p in personas] == esperado


@pytest.mark.parametrize(
    ("desc", "esperado"),
    [
        ("Empresa: Acme\nContacto: Ana Pérez <ana@acme.test>", ("Ana Pérez", None, "ana@acme.test")),
        ("Empresa: Acme\nContacto: Ana Pérez <ana@acme.test>, CEO", ("Ana Pérez", "CEO", "ana@acme.test")),
        (
            "Empresa: Acme\nContacto: Ana Pérez <ana@acme.test>\nEmail: otra@acme.test",
            ("Ana Pérez", None, "otra@acme.test"),
        ),
        ("Empresa: Acme\nContacto: Ana Pérez <sin correo>", ("Ana Pérez <sin correo>", None, None)),
    ],
)
def test_single_contact_angle_bracket_email_table(desc, esperado):
    personas = extract_all_persons_from_description(desc)
    assert [(p["full_name"], p["job_area"], p["email"]) for p in personas] == [esperado]


def test_parsed_event_uses_angle_bracket_email():
    """Google Calendar entrega la descripción en HTML: el «<» tecleado llega como «&lt;»."""
    parsed = parse_calendar_event_for_dossiers(
        {
            "tema": "Reunión — Acme",
            "descripcion": "Empresa: Acme<br>Contacto 1: Ana Pérez &lt;ana@acme.test&gt;",
        }
    )
    assert (parsed["person_name"], parsed["person_email"]) == ("Ana Pérez", "ana@acme.test")


@pytest.mark.parametrize(
    ("desc", "empresa"),
    [
        ("Empresa: Acme Corp Username: ana", "Acme Corp Username: ana"),
        ("Empresa: Laboratorio Genome: análisis", "Laboratorio Genome: análisis"),
        ("Empresa: Acme Corp Contacto: Ana", "Acme Corp"),
        ("Empresa: Acme Corp Email: ana@acme.test", "Acme Corp"),
    ],
)
def test_label_inside_a_word_does_not_cut_the_value(desc, empresa):
    assert extract_company_from_description(desc) == empresa


@pytest.mark.parametrize(
    "desc",
    [
        "Empresa: Acme\nSecuenciación del genome: análisis",
        "Empresa: Acme\nUsername: ana",
        "Empresa: Acme\nNickname: ana",
    ],
)
def test_person_label_inside_a_word_is_not_a_contact(desc):
    assert extract_all_persons_from_description(desc) == []


def test_job_label_inside_a_word_is_not_a_job():
    assert extract_person_from_description("Contacto: Ana\nControl: semanal") == ("Ana", None, None)


@pytest.mark.parametrize(
    ("desc", "esperado"),
    [
        ("Confirma: asistencia", False),
        ("Secuenciación del genome: análisis", False),
        ("Username: ana", False),
        ("Empresa: Acme", True),
        ("Firma: Acme", True),
        ("Contacto: Ana", True),
    ],
)
def test_business_signals_require_whole_label(desc, esperado):
    assert has_business_meeting_signals({"tema": "Revisión", "descripcion": desc}) is esperado


def test_person_hint_regex_source_requires_whole_label():
    rx = re.compile(person_hint_regex_source(), re.IGNORECASE)
    for desc in ("Secuenciación del genome: análisis", "Username: ana", "Nickname: ana"):
        assert not rx.search(desc), desc
    for desc in ("Nome: João", "Name: Ana", "Contacto 1: Ana <ana@gmail.com>"):
        assert rx.search(desc), desc
