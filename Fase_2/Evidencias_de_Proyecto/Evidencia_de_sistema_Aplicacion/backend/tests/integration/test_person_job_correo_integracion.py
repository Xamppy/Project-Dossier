"""S6.1 · CA10–CA12 de punta a punta: job de Personas real contra Postgres y correo real
contra el servidor SMTP de loopback (``servidor_smtp``). PDL y el LLM son dobles.

Requiere ``TEST_DATABASE_URL`` (ver ``pg_vacia`` en conftest.py).
"""
from __future__ import annotations

import io
import json
import logging
import uuid
from types import SimpleNamespace

import pytest
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.db.models import Dossier, DossierGenerationJob
from dossier.services import dossier_generation_job_service as servicio
from dossier.services import dossier_progress_events as bus
from dossier.services import pdl_research, person_research_service

CORREO_USUARIO = "s61@example.com"
PERSONA_PDL = {
    "id": "pdl-ana-1",
    "full_name": "Ana Prueba",
    "job_title": "Directora",
    "job_company_name": "Empresa de Prueba SA",
}


def _payload_valido() -> str:
    return json.dumps(
        {
            "meeting_context": {},
            "executive_summary": "Ana Prueba dirige Empresa de Prueba SA.",
            "participants": [{"name": "Ana Prueba"}],
            "conversation_starters": [],
            "final_recommendation": {"overall_risk": "low", "decision": "proceed"},
            "confidence_assessment": {"high_confidence": ["Cargo actual."]},
        }
    )


class PdlFalso:
    def person_enrich(self, params):
        return {"data": dict(PERSONA_PDL), "likelihood": 8}

    def person_search(self, *, sql=None, query=None, size=5):
        return {"data": [], "total": 0}


@pytest.fixture
def base(pg_vacia, alembic_cfg, monkeypatch):
    command.upgrade(alembic_cfg, "head")
    with pg_vacia.begin() as conn:
        org_id = conn.execute(
            text(
                "INSERT INTO organizations (name, slug, plan, credits_balance) "
                "VALUES ('Org', 'org-s61', 'pro', 100) RETURNING id"
            )
        ).scalar_one()
        user_id = conn.execute(
            text("INSERT INTO users (email) VALUES (:e) RETURNING id"), {"e": CORREO_USUARIO}
        ).scalar_one()
    monkeypatch.setattr(pdl_research, "PdlClient", PdlFalso)
    monkeypatch.setattr(person_research_service, "deepseek_api_key", lambda: "clave-de-prueba")
    monkeypatch.setattr(
        person_research_service, "analyze_person_with_google_search", lambda **_: "## IA\n\nAna."
    )
    monkeypatch.setattr(
        person_research_service, "analyze_person_profile_bundle", lambda **_: "## Respaldo\n\nAna."
    )
    jobs: list[uuid.UUID] = []
    yield SimpleNamespace(engine=pg_vacia, org_id=org_id, user_id=user_id, jobs=jobs)
    for job_id in jobs:
        bus.forget(job_id)


def _procesar(base) -> tuple[dict, Dossier | None]:
    pedido = {
        "full_name": "Ana Prueba",
        "company": "Empresa de Prueba SA",
        "email": "ana@empresa.example",
        "research_source": "pdl",
        "max_profiles": 1,
    }
    with Session(base.engine) as db:
        job = DossierGenerationJob(
            organization_id=base.org_id,
            requested_by_user_id=base.user_id,
            status="queued",
            job_type="person_manual",
            external_event_id=f"person:{uuid.uuid4().hex}",
            reunion_snapshot={"person_request": pedido},
            depth_level="basic",
            meeting_label="Ana Prueba",
            credits_estimated=1,
        )
        db.add(job)
        db.commit()
        job_id = job.id
    base.jobs.append(job_id)
    with Session(base.engine) as db:
        servicio.process_dossier_generation_job(db, job_id)
    with Session(base.engine) as db:
        datos = servicio.serialize_job(db.get(DossierGenerationJob, job_id))
        saved = (datos["result"] or {}).get("saved_dossier") or {}
        dossier = db.get(Dossier, uuid.UUID(saved["id"])) if saved.get("id") else None
        return datos, dossier


def test_ca10_job_completado_envia_el_dossier_completo_al_solicitante(base, servidor_smtp, llm_falso):
    llm_falso(_payload_valido())

    datos, dossier = _procesar(base)

    assert datos["status"] == "completed"
    (msg,) = servidor_smtp.mensajes
    assert servidor_smtp.sobres[0]["to"] == [CORREO_USUARIO]
    assert msg["Subject"] == "Dossier: Ana Prueba"
    html = msg.get_body(("html",)).get_content()
    assert "Ana Prueba dirige Empresa de Prueba SA." in html
    assert f"/dashboard/dossiers/{dossier.id}" in html
    (adjunto,) = list(msg.iter_attachments())
    assert adjunto.get_filename() == "dossier-ana-prueba.pdf"
    pdf = PdfReader(io.BytesIO(adjunto.get_content()))
    assert "Ana Prueba dirige Empresa de Prueba SA." in " ".join(p.extract_text() for p in pdf.pages)
    assert dossier.email_sent is True
    assert dossier.email_sent_at is not None
    assert dossier.email_recipients == [CORREO_USUARIO]


def test_ca11_sin_smtp_configurado_no_se_envia(base, servidor_smtp, llm_falso, monkeypatch):
    llm_falso(_payload_valido())
    monkeypatch.setenv("SMTP_SECURITY", "starttls")  # exige usuario y contraseña, que no hay

    datos, dossier = _procesar(base)

    assert datos["status"] == "completed"
    assert servidor_smtp.conexiones == 0
    assert dossier.email_sent is False


def test_ca11_job_fallido_no_envia(base, servidor_smtp, monkeypatch):
    monkeypatch.setattr(person_research_service, "deepseek_api_key", lambda: "")

    datos, _ = _procesar(base)

    assert datos["status"] == "failed"
    assert servidor_smtp.conexiones == 0


def test_ca12_fallo_smtp_no_cambia_el_job_ni_el_dossier(base, servidor_smtp, llm_falso, caplog):
    llm_falso(_payload_valido())
    servidor_smtp.rechazar = True

    with caplog.at_level(logging.WARNING, logger="dossier.services.dossier_email"):
        datos, dossier = _procesar(base)

    assert datos["status"] == "completed"
    assert dossier.status == "complete"
    assert dossier.email_sent is False
    assert dossier.email_recipients == []
    assert any(str(dossier.id) in r.getMessage() for r in caplog.records)
