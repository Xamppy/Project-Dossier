"""UX-ADMIN-01 · Tope de dossiers generándose a la vez por usuario según el plan (Postgres).

Ver specs/proposals/UX-ADMIN-01-limites-por-plan.md. Requiere ``TEST_DATABASE_URL``.
La administración de los límites está en tests/security/test_limites_plan_admin.py.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.security.jwt_tokens import create_access_token

RUTA_PERSONA = "/dossiers/person/research"


def org(c, nombre: str, plan: str):
    return c.execute(
        text(
            "INSERT INTO organizations (name, slug, plan, credits_balance, credits_monthly_limit) "
            "VALUES (:n, :s, :p, 1000, 1000) RETURNING id"
        ),
        {"n": nombre, "s": nombre.lower(), "p": plan},
    ).scalar_one()


def usuario(c, email: str, org_id, role: str = "user"):
    uid = c.execute(text("INSERT INTO users (email) VALUES (:e) RETURNING id"), {"e": email}).scalar_one()
    c.execute(
        text(
            "INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) "
            "VALUES (:o, :u, :r, true)"
        ),
        {"o": org_id, "u": uid, "r": role},
    )
    return uid


def cliente(user_id, org_id, role: str = "user") -> TestClient:
    tok = create_access_token(user_id=str(user_id), email="x@example.com", organization_id=str(org_id), role=role)
    return TestClient(app, headers={"Authorization": f"Bearer {tok}"}, raise_server_exceptions=False)


def pedir_persona(c: TestClient, nombre: str):
    return c.post(RUTA_PERSONA, json={"full_name": nombre, "company": "Acme", "async_mode": True, "max_profiles": 1})


def trabajos(engine, user_id, estado: str | None = None) -> int:
    sql = "SELECT count(*) FROM dossier_generation_jobs WHERE requested_by_user_id = :u"
    if estado:
        sql += " AND status = :s"
    with engine.connect() as c:
        return c.execute(text(sql), {"u": user_id, "s": estado}).scalar_one()


def trabajo_activo(engine, org_id, user_id, *, job_type: str = "person_manual", hace_minutos: int = 0) -> None:
    from datetime import UTC, datetime, timedelta

    from dossier.db.models import DossierGenerationJob

    with Session(engine) as s:
        s.add(
            DossierGenerationJob(
                organization_id=org_id,
                requested_by_user_id=user_id,
                status="running",
                job_type=job_type,
                created_at=datetime.now(UTC) - timedelta(minutes=hace_minutos),
            )
        )
        s.commit()


@pytest.fixture
def base(pg_vacia, alembic_cfg, monkeypatch) -> Iterator[SimpleNamespace]:
    # Sin crédito real de por medio: el cobro no es lo que se prueba aquí.
    monkeypatch.setenv("DOSSIER_CHARGE_CREDITS", "false")
    command.upgrade(alembic_cfg, "head")
    m = SimpleNamespace(engine=pg_vacia)
    with pg_vacia.begin() as c:
        m.free = org(c, "Libre", "free")
        m.pro = org(c, "Pro", "pro")
        m.u_free = usuario(c, "free@libre.com", m.free)
        m.u_pro = usuario(c, "uno@pro.com", m.pro)
        m.u_pro2 = usuario(c, "dos@pro.com", m.pro)

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    yield m
    app.dependency_overrides.clear()


def test_ca1_la_migracion_deja_los_valores_iniciales(base):
    with base.engine.connect() as c:
        filas = dict(c.execute(text("SELECT plan, max_concurrent_dossiers FROM plan_settings")).all())
    assert filas == {"free": 1, "pro": 3, "enterprise": 10}


def test_ca1_downgrade_quita_la_tabla_y_upgrade_la_repone(base, alembic_cfg):
    command.downgrade(alembic_cfg, "-1")
    with base.engine.connect() as c:
        assert c.execute(text("SELECT to_regclass('plan_settings')")).scalar_one() is None
    command.upgrade(alembic_cfg, "head")
    with base.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM plan_settings")).scalar_one() == 3


def test_ca2_free_puede_uno_y_el_segundo_da_409(base):
    c = cliente(base.u_free, base.free)
    assert pedir_persona(c, "Persona Uno").status_code == 200
    resp = pedir_persona(c, "Persona Dos")
    assert resp.status_code == 409
    assert resp.json()["detail"] == {"code": "CONCURRENT_DOSSIER_LIMIT", "limit": 1, "active": 1}
    assert trabajos(base.engine, base.u_free) == 1


def test_ca2_pro_puede_tres(base):
    c = cliente(base.u_pro, base.pro)
    assert [pedir_persona(c, f"Persona {i}").status_code for i in range(4)] == [200, 200, 200, 409]


@pytest.mark.parametrize("estado", ["completed", "failed", "cancelled"])
def test_ca3_al_terminar_uno_se_libera_el_cupo(base, estado):
    c = cliente(base.u_free, base.free)
    job_id = pedir_persona(c, "Persona Uno").json()["job_id"]
    with base.engine.begin() as cx:
        cx.execute(text("UPDATE dossier_generation_jobs SET status = :s WHERE id = :i"), {"s": estado, "i": job_id})
    assert pedir_persona(c, "Persona Dos").status_code == 200


def test_ca4_el_tope_es_por_usuario(base):
    uno, dos = cliente(base.u_pro, base.pro), cliente(base.u_pro2, base.pro)
    for i in range(3):
        assert pedir_persona(uno, f"P{i}").status_code == 200
    assert pedir_persona(uno, "P3").status_code == 409
    assert pedir_persona(dos, "Q0").status_code == 200


def test_ca5_un_trabajo_colgado_hace_mas_de_30_minutos_no_cuenta(base):
    trabajo_activo(base.engine, base.free, base.u_free, hace_minutos=45)
    assert pedir_persona(cliente(base.u_free, base.free), "Persona Uno").status_code == 200


def test_ca5_la_ventana_es_configurable(base, monkeypatch):
    monkeypatch.setenv("DOSSIER_CONCURRENCY_WINDOW_MINUTES", "60")
    trabajo_activo(base.engine, base.free, base.u_free, hace_minutos=45)
    assert pedir_persona(cliente(base.u_free, base.free), "Persona Uno").status_code == 409


def test_ca5_trabajos_que_no_son_pedidos_del_usuario_no_cuentan(base):
    trabajo_activo(base.engine, base.free, base.u_free, job_type="calendar_auto")
    assert pedir_persona(cliente(base.u_free, base.free), "Persona Uno").status_code == 200


def test_ca6_un_pedido_duplicado_devuelve_el_activo_aunque_el_tope_este_lleno(base):
    c = cliente(base.u_free, base.free)
    primero = pedir_persona(c, "Persona Uno").json()["job_id"]
    repetido = pedir_persona(c, "Persona Uno")
    assert repetido.status_code == 200
    assert repetido.json()["job_id"] == primero


def test_el_limite_cambiado_en_la_tabla_se_aplica_enseguida(base):
    with base.engine.begin() as c:
        c.execute(text("UPDATE plan_settings SET max_concurrent_dossiers = 2 WHERE plan = 'free'"))
    c = cliente(base.u_free, base.free)
    assert [pedir_persona(c, f"P{i}").status_code for i in range(3)] == [200, 200, 409]


def test_sin_fila_del_plan_se_usa_el_valor_inicial(base):
    with base.engine.begin() as c:
        c.execute(text("DELETE FROM plan_settings WHERE plan = 'free'"))
    c = cliente(base.u_free, base.free)
    assert [pedir_persona(c, f"P{i}").status_code for i in range(2)] == [200, 409]


# --- Calendario (varias reuniones en una petición) ---------------------------


def _encolar_reuniones(engine, user_id, org_id, ids: list[str]):
    from dossier.api.app import _enqueue_calendar_dossier_jobs
    from dossier.db.models import Organization, User

    with Session(engine) as s:
        return _enqueue_calendar_dossier_jobs(
            s,
            user=s.get(User, user_id),
            org=s.get(Organization, org_id),
            reuniones=[{"id": i, "tema": f"Reunión {i}", "participantes": "Jane Doe <jane@acme.com>"} for i in ids],
            calendar_provider="google",
            depth="basic",
        )


def test_ca7_calendario_que_supera_el_tope_no_encola_ninguna(base):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as err:
        _encolar_reuniones(base.engine, base.u_pro, base.pro, ["e1", "e2", "e3", "e4"])
    assert err.value.status_code == 409
    assert err.value.detail["code"] == "CONCURRENT_DOSSIER_LIMIT"
    assert trabajos(base.engine, base.u_pro) == 0


def test_ca7_calendario_dentro_del_tope_encola_todas(base):
    salida = _encolar_reuniones(base.engine, base.u_pro, base.pro, ["e1", "e2", "e3"])
    assert len(salida["jobs"]) == 3
    assert trabajos(base.engine, base.u_pro, "queued") == 3


def test_ca7_reuniones_ya_en_curso_no_cuentan_dos_veces(base):
    _encolar_reuniones(base.engine, base.u_pro, base.pro, ["e1", "e2"])
    salida = _encolar_reuniones(base.engine, base.u_pro, base.pro, ["e1", "e2", "e3"])
    assert len(salida["jobs"]) == 3
    assert trabajos(base.engine, base.u_pro) == 3


def test_ca7_persona_y_calendario_comparten_el_tope(base):
    from fastapi import HTTPException

    c = cliente(base.u_pro, base.pro)
    assert pedir_persona(c, "Persona Uno").status_code == 200
    with pytest.raises(HTTPException):
        _encolar_reuniones(base.engine, base.u_pro, base.pro, ["e1", "e2", "e3"])
    _encolar_reuniones(base.engine, base.u_pro, base.pro, ["e1", "e2"])
    assert pedir_persona(c, "Persona Dos").status_code == 409


# --- Concurrencia -------------------------------------------------------------


def test_ca8_pedidos_simultaneos_no_superan_el_tope(base):
    respuestas: list[int] = []
    barrera = threading.Barrier(6)

    def pedir(i: int) -> None:
        c = cliente(base.u_pro, base.pro)
        barrera.wait()
        respuestas.append(pedir_persona(c, f"Simultánea {i}").status_code)

    hilos = [threading.Thread(target=pedir, args=(i,)) for i in range(6)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(respuestas) == [200, 200, 200, 409, 409, 409]
    assert trabajos(base.engine, base.u_pro) == 3
