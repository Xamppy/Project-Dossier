"""UX-CAL-03 · Personas de una reunión y dossier de la persona elegida (CA3, CA5, CA6).

Especificación: ``specs/proposals/UX-CAL-03-reunion-varias-personas.md``. Sin red ni base de datos.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from dossier.services import google_calendar_api as google
from dossier.services import graph_calendar as graph
from dossier.services.calendar_event_dossiers import parse_calendar_event_for_dossiers
from dossier.services.dossier_generation_job_service import estimate_reunion_credits
from dossier.services.graph_calendar import coerce_reunion_payload, merge_reunion_payload
from dossier.services.meeting_people import (
    correos_propios,
    elegir_persona,
    personas_de_la_reunion,
    requiere_elegir_persona,
)

YO = "yo@mi-empresa.test"


def _google(**extra):
    """Como la reunión del informe: organiza una persona que también figura como asistente."""
    return {
        "id": "g1",
        "summary": "Avance del proyecto",
        "description": "",
        "start": {"dateTime": "2026-11-30T10:00:00Z"},
        "end": {"dateTime": "2026-11-30T11:00:00Z"},
        "organizer": {"email": "carla.diaz@acme.test"},
        "attendees": [
            {"email": YO, "self": True},
            {"email": "max@acme.test"},
            {"email": "Carla.Diaz@acme.test", "displayName": "Carla Díaz"},
            {"email": "sala-3@resource.calendar.google.com", "resource": True},
        ],
        **extra,
    }


def _graph(**extra):
    def quien(nombre, correo, tipo="required"):
        return {"type": tipo, "emailAddress": {"name": nombre, "address": correo}}

    return {
        "id": "m1",
        "subject": "Avance del proyecto",
        "body": {"contentType": "text", "content": ""},
        "start": {"dateTime": "2026-11-30T10:00:00.0000000"},
        "end": {"dateTime": "2026-11-30T11:00:00.0000000"},
        "organizer": {"emailAddress": {"name": "Carla Díaz", "address": "carla.diaz@acme.test"}},
        "attendees": [
            quien("Yo Mismo", YO.upper()),
            quien("max@acme.test", "max@acme.test"),
            quien("Carla Díaz", "carla.diaz@acme.test"),
            quien("Sala 3", "sala-3@acme.test", "resource"),
        ],
        **extra,
    }


@pytest.mark.parametrize(
    "reunion",
    [google.normalizar_evento_google(_google()), graph.normalizar_evento(_graph())],
    ids=["google", "outlook"],
)
def test_ca3_ni_el_usuario_ni_las_salas_cuentan_y_nadie_se_repite(reunion):
    personas = personas_de_la_reunion(reunion, {YO})
    assert [(p["id"], p["nombre"], p["correo"]) for p in personas] == [
        ("carla.diaz@acme.test", "Carla Díaz", "carla.diaz@acme.test"),
        ("max@acme.test", "Max", "max@acme.test"),
    ]
    assert requiere_elegir_persona(personas)


def test_la_marca_self_de_google_basta_aunque_el_correo_sea_un_alias():
    personas = personas_de_la_reunion(google.normalizar_evento_google(_google()), set())
    assert YO not in {p["correo"] for p in personas}


def test_un_calendario_compartido_como_organizador_no_es_una_persona():
    evento = _google(organizer={"email": "c_123@group.calendar.google.com", "self": False})
    correos = {p["correo"] for p in personas_de_la_reunion(google.normalizar_evento_google(evento), {YO})}
    assert correos == {"max@acme.test", "carla.diaz@acme.test"}


def test_con_una_sola_persona_no_hay_que_elegir():
    evento = _google(organizer={"email": YO, "self": True}, attendees=[{"email": "max@acme.test"}])
    personas = personas_de_la_reunion(google.normalizar_evento_google(evento), {YO})
    assert len(personas) == 1 and not requiere_elegir_persona(personas)


def test_un_contacto_declarado_y_un_asistente_son_la_misma_persona():
    reunion = {
        "descripcion": "Empresa: Acme\nContacto: Elena Prueba\nCargo: CTO",
        "asistentes": [{"nombre": None, "correo": "eprueba@acme.test", "yo": False}],
    }
    (persona,) = personas_de_la_reunion(reunion, {YO})
    assert persona["nombre"] == "Elena Prueba"
    assert persona["cargo"] == "CTO"
    assert persona["correo"] == "eprueba@acme.test"


def test_contactos_declarados_se_unen_a_su_asistente_por_correo_o_por_nombre():
    reunion = {
        "descripcion": "Contacto 1: Ana Prueba\nCargo 1: CEO\nEmail 1: ana@acme.test\nContacto 2: Beto Ruiz",
        "asistentes": [
            {"nombre": None, "correo": "ana@acme.test", "yo": False},
            {"nombre": None, "correo": "beto.ruiz@acme.test", "yo": False},
            {"nombre": None, "correo": "otro@acme.test", "yo": False},
        ],
    }
    personas = personas_de_la_reunion(reunion, {YO})
    assert [(p["nombre"], p["correo"], p["cargo"]) for p in personas] == [
        ("Ana Prueba", "ana@acme.test", "CEO"),
        ("Beto Ruiz", "beto.ruiz@acme.test", None),
        ("Otro", "otro@acme.test", None),
    ]


def test_un_nombre_de_pila_suelto_no_basta_para_asignar_un_correo():
    """BUG-2026-10-19-02: un correo dudoso no se le pone a nadie."""
    reunion = {
        "descripcion": "Contacto 1: Ana Prueba\nContacto 2: Beto Ruiz",
        "asistentes": [{"nombre": None, "correo": "ana@otra.test", "yo": False}],
    }
    personas = personas_de_la_reunion(reunion, {YO})
    assert [p["correo"] for p in personas] == [None, None, "ana@otra.test"]
    assert len({p["id"] for p in personas}) == 3


def test_los_contactos_declarados_sin_correo_tambien_obligan_a_elegir():
    reunion = {"descripcion": "Contactos: Ana Prueba, Beto Ruiz", "participantes": "No especificados"}
    assert requiere_elegir_persona(personas_de_la_reunion(reunion, {YO}))


def test_el_asunto_no_inventa_personas():
    reunion = {
        "tema": "Reunión con Acme",
        "descripcion": "",
        "asistentes": [{"nombre": None, "correo": "max@acme.test", "yo": False}],
    }
    assert len(personas_de_la_reunion(reunion, {YO})) == 1


def test_un_evento_guardado_antes_de_este_cambio_usa_los_correos_de_participantes():
    reunion = {"descripcion": "", "participantes": f"carla@acme.test (organizador), {YO}, max@acme.test"}
    assert [p["correo"] for p in personas_de_la_reunion(reunion, {YO})] == ["carla@acme.test", "max@acme.test"]


@pytest.mark.parametrize(
    ("correo", "nombre"),
    [
        ("ana.perez@acme.test", "Ana Perez"),
        ("ana_perez23@acme.test", "Ana Perez"),
        ("ana.perez+ventas@acme.test", "Ana Perez"),
        ("12345@acme.test", "12345"),
        ("x@acme.test", "x@acme.test"),
    ],
)
def test_nombre_deducido_del_correo(correo, nombre):
    (p,) = personas_de_la_reunion({"asistentes": [{"nombre": None, "correo": correo, "yo": False}]}, set())
    assert p["nombre"] == nombre


def test_correos_propios_reune_la_cuenta_y_el_calendario():
    user = SimpleNamespace(email=" Yo@Mi-Empresa.test ")
    integracion = SimpleNamespace(provider_email="yo.calendario@gmail.com")
    assert correos_propios(user, integracion) == {YO, "yo.calendario@gmail.com"}
    assert correos_propios(None, None) == set()


# ── La persona elegida ───────────────────────────────────────────────────────


REUNION = {
    "id": "g1",
    "tema": "Reunión comercial — Tesla",
    "descripcion": "Contacto 1: Ana Prueba\nCargo 1: CEO\nEmail 1: ana@acme.test\nContacto 2: Beto Ruiz",
    "participantes": "ana@acme.test, max@otra-empresa.test",
    "asistentes": [
        {"nombre": None, "correo": "ana@acme.test", "yo": False},
        {"nombre": None, "correo": "max@otra-empresa.test", "yo": False},
    ],
}


def _con_empresa():
    return {**REUNION, "descripcion": "Empresa: Acme SpA\n" + REUNION["descripcion"]}


def _elegir(persona_id, reunion=REUNION):
    return elegir_persona(reunion, persona_id, personas_de_la_reunion(reunion, {YO}))


def test_ca5_el_parser_entrega_solo_la_persona_elegida():
    parsed = parse_calendar_event_for_dossiers(_elegir("ana@acme.test"))
    assert parsed["persons"] == [
        {"index": 1, "full_name": "Ana Prueba", "job_area": "CEO", "country": None, "email": "ana@acme.test"}
    ]
    assert (parsed["person_name"], parsed["person_email"]) == ("Ana Prueba", "ana@acme.test")


def test_ca5_una_persona_sin_correo_no_hereda_el_de_otra():
    parsed = parse_calendar_event_for_dossiers(_elegir("contacto:beto ruiz"))
    assert [(p["full_name"], p["email"]) for p in parsed["persons"]] == [("Beto Ruiz", None)]
    assert parsed["person_email"] is None


def test_la_empresa_adivinada_del_asunto_no_se_genera():
    parsed = parse_calendar_event_for_dossiers(_elegir("ana@acme.test"))
    assert parsed["company_corporate"] == ""


def test_la_empresa_declarada_identifica_a_la_persona_pero_no_genera_su_dossier():
    parsed = parse_calendar_event_for_dossiers(_elegir("max@otra-empresa.test", _con_empresa()))
    assert parsed["company_person"] == "Acme SpA"
    assert (parsed["company"], parsed["company_corporate"], parsed["company_corporate_source"]) == ("", "", "")


@pytest.mark.parametrize(
    ("correo", "empresa"),
    [("max@otra-empresa.test", "Otra Empresa"), ("max@mail.acme.co.uk", "Acme"), ("max@gmail.com", "")],
)
def test_sin_empresa_declarada_se_usa_la_del_dominio_corporativo(correo, empresa):
    reunion = {"tema": "Avance", "asistentes": [{"nombre": None, "correo": c, "yo": False} for c in (correo, "b@b.test")]}
    assert parse_calendar_event_for_dossiers(_elegir(correo, reunion))["company_person"] == empresa


def test_una_persona_que_no_es_de_la_reunion_no_se_puede_elegir():
    with pytest.raises(LookupError):
        _elegir("intrusa@acme.test")


def test_ca6_la_eleccion_sobrevive_a_la_relectura_del_evento():
    fresco = google.normalizar_evento_google(_google())
    fusion = merge_reunion_payload(_elegir("ana@acme.test"), fresco)
    assert parse_calendar_event_for_dossiers(fusion)["person_name"] == "Ana Prueba"
    assert fusion["asistentes"] == fresco["asistentes"]


def test_ca7_el_cliente_no_puede_inyectar_la_persona_en_la_reunion():
    limpio = coerce_reunion_payload({**_elegir("ana@acme.test"), "personas": [{"id": "x"}]})
    assert "_persona_elegida" not in limpio and "personas" not in limpio
    assert len(limpio["asistentes"]) == 2


@pytest.mark.parametrize("basura", [None, "texto", [1, None, {}], [{"correo": 5, "nombre": ["x"]}], {"a": 1}])
def test_asistentes_con_forma_invalida_no_rompen(basura):
    limpio = coerce_reunion_payload({"id": "g1", "tema": "Hola", "asistentes": basura})
    assert personas_de_la_reunion(limpio, {YO}) == []


@pytest.mark.parametrize("reunion", [REUNION, _con_empresa()], ids=["sin_empresa", "con_empresa"])
def test_el_costo_estimado_es_el_de_una_sola_persona(reunion):
    """Pro incluye el dossier de empresa (3 créditos): al elegir persona no se genera ni se estima."""
    assert estimate_reunion_credits(_elegir("ana@acme.test", reunion), plan="pro") == 1
