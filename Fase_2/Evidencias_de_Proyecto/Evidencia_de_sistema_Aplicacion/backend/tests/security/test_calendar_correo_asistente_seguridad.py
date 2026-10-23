"""BUG-2026-10-19-02 · Datos personales y cobro entre asistentes de una misma reunión.

Si a un asistente se le consulta PDL con el correo de otro, PDL devuelve (y cobra)
el perfil equivocado, y el dossier queda guardado con el correo de otra persona.

Sin base ni red: PDL es un doble que encuentra a Ana solo por su correo, y la
sesión de base es un doble que recoge lo que se guardaría.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from dossier.db.models import Dossier
from dossier.graphs.corporate_dossier_graph import CorporateDossierResult
from dossier.services import calendar_event_dossiers as cal
from dossier.services import pdl_research, person_research_service

CORREO_ANA = "ana@example.com"
ID_PDL_ANA = "pdl-ficticio-ana"

REUNION = {
    "tema": "Kick-off con Empresa de Prueba SA",
    "descripcion": (
        "Empresa: Empresa de Prueba SA\n"
        f"Contacto 1: Ana Prueba\nCargo 1: Directora general\nEmail 1: {CORREO_ANA}\n"
        "Contacto 2: Beto Ficticio\nCargo 2: Gerente"
    ),
    "participantes": CORREO_ANA,
    "inicio": "2026-10-20T10:00:00Z",
}


class _Sesion:
    def __init__(self):
        self.added: list[object] = []

    def get(self, model, pk):
        return None

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass


@pytest.fixture
def pdl_que_encuentra_a_ana(monkeypatch):
    """PDL que devuelve el perfil de Ana a quien pregunte por su correo; registra los aciertos."""
    estado: dict[str, Any] = {"actual": None, "aciertos": []}

    class PdlFalso:
        def __init__(self, *_a, **_k):
            pass

        def person_enrich(self, params):
            if params.get("email") != CORREO_ANA:
                return None
            estado["aciertos"].append(estado["actual"])
            return {
                "data": {
                    "id": ID_PDL_ANA,
                    "full_name": "Ana Prueba",
                    "job_title": "Directora general",
                    "job_company_name": "Empresa de Prueba SA",
                    "linkedin_url": "https://www.linkedin.com/in/ana-prueba-ficticia",
                },
                "likelihood": 9,
            }

        def person_search(self, **_):
            return {"data": [], "total": 0}

    investigar_real = cal.run_person_research

    def investigar(req, **kwargs):
        estado["actual"] = req.full_name
        try:
            return investigar_real(req, **kwargs)
        finally:
            estado["actual"] = None

    monkeypatch.setattr(pdl_research, "PdlClient", PdlFalso)
    monkeypatch.setattr(cal, "run_person_research", investigar)
    monkeypatch.setattr(person_research_service, "deepseek_api_key", lambda: "")
    monkeypatch.setattr(cal, "redis_person_cache_available", lambda: False)
    monkeypatch.setattr(cal, "redis_corporate_cache_available", lambda: False)
    monkeypatch.setattr(
        cal,
        "run_corporate_dossier_langgraph_detailed",
        lambda **_: CorporateDossierResult(markdown="# Dossier corporativo\n\nResumen.", agents_failed=[], agents_succeeded=[]),
    )
    monkeypatch.setattr(cal, "resolve_corporate_brief", lambda q: (q, "dual"))
    monkeypatch.setenv("PERSON_RESEARCH_PROVIDER", "pdl")
    monkeypatch.setenv("DEEPSEEK_DISABLE_PERSON_WEB", "1")
    return estado


def test_pdl_no_devuelve_ni_cobra_el_perfil_de_ana_para_beto(pdl_que_encuentra_a_ana):
    item = cal.generate_dossiers_from_calendar_event(REUNION, organization_id=uuid.uuid4(), organization_plan="pro")

    assert pdl_que_encuentra_a_ana["aciertos"] == ["Ana Prueba"], "solo Ana consume un acierto de PDL"
    beto = next(p for p in item["dossier_personas"] if p["full_name"] == "Beto Ficticio")
    assert ID_PDL_ANA not in json.dumps(beto["payload"], default=str)


def test_el_dossier_de_beto_no_guarda_el_correo_de_ana(pdl_que_encuentra_a_ana):
    item = cal.generate_dossiers_from_calendar_event(REUNION, organization_id=uuid.uuid4(), organization_plan="pro")
    db = _Sesion()

    cal.persist_calendar_dossiers(
        db, user_id=uuid.uuid4(), org_id=uuid.uuid4(), result=item, calendar_provider="google", generation_duration_ms=1
    )

    personas = {d.subject_name: d for d in db.added if isinstance(d, Dossier) and not d.module_corporate}
    beto = personas["Beto Ficticio"]
    assert beto.subject_email is None
    assert beto.dossier_data["person_filters"]["email"] is None
    assert personas["Ana Prueba"].subject_email == CORREO_ANA


def test_al_guardar_un_asistente_sin_correo_no_toma_el_del_primer_contacto():
    """El guardado no rellena el correo de un asistente con el ``person_email`` del evento."""
    result = {
        "parse": {"tema": "Kick-off", "person_email": CORREO_ANA, "company_person": "Empresa de Prueba SA"},
        "reunion": {"tema": "Kick-off", "inicio": "2026-10-20T10:00:00Z"},
        "dossier_personas": [
            {"index": 1, "full_name": "Ana Prueba", "email": CORREO_ANA, "md": "## Informe\n\nAna."},
            {"index": 2, "full_name": "Beto Ficticio", "email": None, "md": "## Informe\n\nBeto."},
        ],
    }
    db = _Sesion()

    cal.persist_calendar_dossiers(
        db, user_id=uuid.uuid4(), org_id=uuid.uuid4(), result=result, calendar_provider="google", generation_duration_ms=1
    )

    beto = next(d for d in db.added if isinstance(d, Dossier) and d.subject_name == "Beto Ficticio")
    assert beto.subject_email is None
    assert beto.dossier_data["person_filters"]["email"] is None
