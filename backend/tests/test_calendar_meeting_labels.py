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
from dossier.services.calendar_meeting_labels import (
    COMPANY_LABELS,
    COUNTRY_LABELS,
    EMAIL_LABELS,
    EMPRESA_DESC,
    JOB_LABELS,
    PERSON_LABELS,
    person_hint_regex_source,
)

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


# --- BUG-2026-10-19-06: lista de contactos y etiqueta vacía ----------------------------------
# 1. Con etiqueta en plural («Contactos:») la coma o el punto y coma separan personas; con
#    etiqueta singular («Contacto: Ana, CEO») se mantiene «Nombre, Cargo».


@pytest.mark.parametrize(
    ("desc", "nombres"),
    [
        ("Empresa: Acme\nContactos: Ana Pérez, Luis Soto", ["Ana Pérez", "Luis Soto"]),
        ("Contacts: John Smith, Jane Doe, Bob Ray", ["John Smith", "Jane Doe", "Bob Ray"]),
        ("Empresa: Acme\nContatos: João Silva; Maria Souza", ["João Silva", "Maria Souza"]),
        ("Azienda: Acme\nContatti: Edward Dalton, Anna Rossi", ["Edward Dalton", "Anna Rossi"]),
        ("Unternehmen: Acme\nKontakte: Hans Müller, Eva Weber", ["Hans Müller", "Eva Weber"]),
        ("Empresa: Acme\nContactos: Ana Pérez, , Luis Soto.", ["Ana Pérez", "Luis Soto"]),
        ("Empresa: Acme\nContactos - Ana Pérez, Luis Soto", ["Ana Pérez", "Luis Soto"]),
    ],
)
def test_plural_label_comma_separates_people(desc, nombres):
    personas = extract_all_persons_from_description(desc)
    assert [(p["index"], p["full_name"]) for p in personas] == list(enumerate(nombres, start=1))
    assert all(p["job_area"] is None for p in personas)


@pytest.mark.parametrize(
    ("desc", "esperado"),
    [
        (
            "Empresa: Acme\nContactos: Ana Pérez <ana@acme.test>, Luis Soto <luis@acme.test>",
            [("Ana Pérez", "ana@acme.test"), ("Luis Soto", "luis@acme.test")],
        ),
        (
            "Empresa: Acme\nContactos: Ana Pérez <ana@acme.test>; Luis Soto",
            [("Ana Pérez", "ana@acme.test"), ("Luis Soto", None)],
        ),
        (
            "Empresa: Acme\nContactos: Ana Pérez, Luis Soto\nEmail: equipo@acme.test",
            [("Ana Pérez", None), ("Luis Soto", None)],
        ),
    ],
)
def test_plural_list_separates_each_angle_bracket_email(desc, esperado):
    """El correo entre <> es de esa persona (decisión de FO en BUG-05); «Email:» suelto, de nadie."""
    personas = extract_all_persons_from_description(desc)
    assert [(p["full_name"], p["email"]) for p in personas] == esperado


def test_plural_label_first_person_has_no_job_from_comma():
    assert extract_person_from_description("Contactos: Ana Pérez, Luis Soto") == ("Ana Pérez", None, None)


def test_plural_list_does_not_assign_shared_job_to_everyone():
    """«Cargo:» sin número es ambiguo con varias personas: no se reparte a todas."""
    desc = "Empresa: Acme\nContactos: Ana Pérez, Luis Soto\nCargo: CEO\nPaís: Chile"
    personas = extract_all_persons_from_description(desc)
    assert [(p["full_name"], p["job_area"], p["country"]) for p in personas] == [
        ("Ana Pérez", None, None),
        ("Luis Soto", None, None),
    ]


def test_plural_list_parsed_event_has_every_person():
    parsed = parse_calendar_event_for_dossiers(
        {"tema": "Reunión — Acme", "descripcion": "Empresa: Acme\nContactos: Ana Pérez, Luis Soto"}
    )
    assert [p["full_name"] for p in parsed["persons"]] == ["Ana Pérez", "Luis Soto"]
    assert (parsed["person_name"], parsed["person_job"]) == ("Ana Pérez", None)


@pytest.mark.parametrize(
    ("desc", "persona"),
    [
        ("Empresa: Acme\nContactos: Ana Pérez", ("Ana Pérez", None, None)),
        ("Empresa: Acme\nContactos: Ana Pérez\nCargo: CEO", ("Ana Pérez", "CEO", None)),
        ("Empresa: Acme\nContacto: Ana Pérez, CEO", ("Ana Pérez", "CEO", None)),
        ("Company: Acme\nContact: John Smith, CTO", ("John Smith", "CTO", None)),
        ("Nombre: Ana Pérez, Gerente", ("Ana Pérez", "Gerente", None)),
        ("Contacto: Ana Pérez, CEO\nCargo: CTO", ("Ana Pérez, CEO", "CTO", None)),
    ],
)
def test_single_person_keeps_name_comma_job(desc, persona):
    personas = extract_all_persons_from_description(desc)
    assert [(p["full_name"], p["job_area"], p["country"]) for p in personas] == [persona]


# 2. Una etiqueta vacía no captura la línea siguiente si esa línea es otra etiqueta.


@pytest.mark.parametrize(
    "desc",
    [
        "Contacto:\nEmpresa: Acme",
        "Empresa: Acme\nContacto:\nCargo: CEO",
        "Empresa: Acme\nContacto:\n  Email: ana@acme.test",
        "Empresa: Acme\nContacto:\nPaís (opcional): Chile",
        "Empresa: Acme\nContacto 1:\nCargo 1: CEO",
        "Empresa: Acme\nContacto: Empresa: Acme",
        "Empresa: Acme\nContactos:\nCargo: CEO",
    ],
)
def test_empty_person_label_does_not_capture_next_label(desc):
    assert extract_all_persons_from_description(desc) == []


@pytest.mark.parametrize(
    ("desc", "empresa"),
    [
        ("Empresa:\nContacto: Ana Pérez", None),
        ("Empresa:\nCargo: CEO", None),
        ("Empresa:\nPaís (opcional): Chile", None),
        ("Contacto:\nEmpresa: Acme", "Acme"),
        ("Empresa:\nAcme", "Acme"),
        ("Empresa:\n\nAcme Corp", "Acme Corp"),
    ],
)
def test_empty_company_label_does_not_capture_next_label(desc, empresa):
    """
    Se prueba el campo «Empresa:» en sí. `extract_company_from_description` tiene además un
    respaldo por línea, heredado, que lee «Contacto: Ana» como asunto «X: Empresa».
    """
    m = EMPRESA_DESC.search(desc)
    assert (m.group(1) if m else None) == empresa


def test_empty_job_label_does_not_capture_next_label():
    assert extract_person_from_description("Contacto: Ana\nCargo:\nPaís: Chile") == ("Ana", None, "Chile")


def test_empty_numbered_email_does_not_capture_next_label():
    desc = "Contacto 1: Ana\nContacto 2: Luis\nEmail 1:\nEmail 2: luis@acme.test"
    personas = extract_numbered_persons_from_description(desc)
    assert [(p["full_name"], p["email"]) for p in personas] == [
        ("Ana", None),
        ("Luis", "luis@acme.test"),
    ]


@pytest.mark.parametrize(
    ("desc", "nombre"),
    [
        ("Contacto:\nAna Pérez", "Ana Pérez"),
        ("Contacto:\n\nAna Pérez", "Ana Pérez"),
        ("Contacto:\nClient Services Team", "Client Services Team"),
        ("Contacto:\nEmpresario Ana Pérez", "Empresario Ana Pérez"),
    ],
)
def test_empty_person_label_still_takes_next_line_value(desc, nombre):
    assert extract_person_from_description(desc)[0] == nombre


@pytest.mark.parametrize(
    ("desc", "esperado"),
    [
        ("Contacto:\nEmpresa: Acme", False),
        ("Empresa: Acme\nContacto:\nCargo: CEO", False),
        ("Empresa: Acme\nContacto 1:\nCargo 1: CEO", False),
        ("Empresa: Acme\nContacto: Empresa: Acme", False),
        ("Empresa: Acme\nContacto:\n  Email: ana@acme.test", False),
        ("Empresa: Acme\nContacto:\nPaís (opcional): Chile", False),
        ("Contacto:\nAna Pérez", True),
        ("Contacto:\n\nAna Pérez", True),
        ("Contacto:\nClient Services Team", True),
        ("Contacto:\nEmpresa: Acme\nContacto 1: Ana", True),
    ],
)
def test_person_hint_regex_source_ignores_empty_label(desc, esperado):
    rx = re.compile(person_hint_regex_source(), re.IGNORECASE)
    assert bool(rx.search(desc)) is esperado


@pytest.mark.parametrize(
    ("grupo", "backend"),
    [
        ("company", COMPANY_LABELS),
        ("person", PERSON_LABELS),
        ("job", JOB_LABELS),
        ("country", COUNTRY_LABELS),
        ("email", EMAIL_LABELS),
    ],
)
def test_frontend_label_groups_match_backend(grupo, backend):
    """El aviso del frontend reconoce «otra etiqueta» con las mismas listas que el backend."""
    text = _FRONTEND_LABELS.read_text(encoding="utf-8")
    bloque = re.search(rf"\b{grupo}:\s*\[(.*?)\]", text, flags=re.DOTALL)
    assert bloque, f"No se encontró CALENDAR_FIELD_LABELS.{grupo} en el frontend"
    assert tuple(re.findall(r'"([^"]+)"', bloque.group(1))) == backend
