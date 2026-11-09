"""S6.7 · Pruebas negativas de aislamiento entre organizaciones (contra Postgres).

No comprueban que algo funcione, sino que algo NO sea posible: que un usuario de la
organización A lea, modifique o siquiera detecte un recurso de la organización B.

Escenario (fixture ``mundo``):

- Organización A: ``a_admin`` (admin) y ``a_user`` (user), con un dossier y un trabajo.
- Organización B: ``b_admin`` (admin) y ``b_user`` (user), con un dossier en carpeta,
  alertas, prensa, trayectoria, una compartición, un trabajo y una invitación.
- ``ambos``: miembro de A y de B (user en las dos), dueño de un dossier en B.

Se ataca con el usuario más privilegiado de A (su admin): si él no llega a B, nadie de A
llega. La regla esperada es 404 (no 403) para un id ajeno, con la misma respuesta que
un id inexistente: así la API no revela que el recurso existe en otra organización.

Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import DossierGenerationJob
from dossier.security.jwt_tokens import create_access_token

# Textos únicos de B: si aparecen en una respuesta a A, hubo fuga.
SECRETO_SUJETO = "Sujeto-Secreto-B"
SECRETO_ALERTA = "Alerta-Secreta-B"
SECRETO_PRENSA = "Titular-Secreto-B"
SECRETO_CARGO = "Empresa-Secreta-B"
CORREO_B_ADMIN = "admin@org-b.com"
CORREO_B_USER = "usuario@org-b.com"
CORREO_INVITADO_B = "invitado@org-b.com"

# Tablas de B cuyo contenido no puede cambiar por acciones de A.
TABLAS_VIGILADAS = (
    "dossiers",
    "dossier_shares",
    "dossier_alerts",
    "dossier_media_mentions",
    "dossier_career_entries",
    "dossier_generation_jobs",
    "org_memberships",
    "org_invites",
)


def _token(user, org, role: str, email: str = "x@example.com") -> str:
    return create_access_token(user_id=str(user), email=email, organization_id=str(org), role=role)


def _cliente(token: str) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {token}"}, raise_server_exceptions=False)


def _org(c, nombre: str):
    return c.execute(
        text("INSERT INTO organizations (name, slug) VALUES (:n, :s) RETURNING id"),
        {"n": nombre, "s": nombre.lower()},
    ).scalar_one()


def _usuario(c, email: str):
    return c.execute(text("INSERT INTO users (email) VALUES (:e) RETURNING id"), {"e": email}).scalar_one()


def _miembro(c, org, user, role: str, principal: bool) -> None:
    c.execute(
        text(
            "INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) "
            "VALUES (:o, :u, :r, :p)"
        ),
        {"o": org, "u": user, "r": role, "p": principal},
    )


def _dossier(c, org, user, sujeto: str, carpeta=None):
    return c.execute(
        text(
            "INSERT INTO dossiers (organization_id, requested_by_user_id, status, subject_name, "
            "dossier_folder_id, dossier_data) "
            "VALUES (:o, :u, 'complete', :s, :f, CAST(:d AS JSONB)) RETURNING id"
        ),
        {"o": org, "u": user, "s": sujeto, "f": carpeta, "d": json.dumps({"markdown": f"# {sujeto}"})},
    ).scalar_one()


def _foto_de_b(engine, org_b) -> dict[str, list]:
    """Contenido de las tablas vigiladas que pertenece a B (o a sus dossiers)."""
    consultas = {
        "dossiers": "SELECT * FROM dossiers WHERE organization_id = :o",
        "dossier_shares": (
            "SELECT s.* FROM dossier_shares s JOIN dossiers d ON d.id = s.dossier_id WHERE d.organization_id = :o"
        ),
        "dossier_alerts": (
            "SELECT x.* FROM dossier_alerts x JOIN dossiers d ON d.id = x.dossier_id WHERE d.organization_id = :o"
        ),
        "dossier_media_mentions": (
            "SELECT x.* FROM dossier_media_mentions x JOIN dossiers d ON d.id = x.dossier_id "
            "WHERE d.organization_id = :o"
        ),
        "dossier_career_entries": (
            "SELECT x.* FROM dossier_career_entries x JOIN dossiers d ON d.id = x.dossier_id "
            "WHERE d.organization_id = :o"
        ),
        "dossier_generation_jobs": "SELECT * FROM dossier_generation_jobs WHERE organization_id = :o",
        "org_memberships": "SELECT * FROM org_memberships WHERE organization_id = :o",
        "org_invites": "SELECT * FROM org_invites WHERE organization_id = :o",
    }
    assert set(consultas) == set(TABLAS_VIGILADAS)
    with engine.connect() as c:
        return {
            tabla: sorted(tuple(map(str, fila)) for fila in c.execute(text(sql), {"o": org_b}).all())
            for tabla, sql in consultas.items()
        }


@pytest.fixture
def mundo(pg_vacia, alembic_cfg) -> Iterator[SimpleNamespace]:
    command.upgrade(alembic_cfg, "head")
    m = SimpleNamespace(engine=pg_vacia)
    with pg_vacia.begin() as c:
        m.org_a, m.org_b = _org(c, "A"), _org(c, "B")
        m.a_admin = _usuario(c, "admin@org-a.com")
        m.a_user = _usuario(c, "usuario@org-a.com")
        m.b_admin = _usuario(c, CORREO_B_ADMIN)
        m.b_user = _usuario(c, CORREO_B_USER)
        m.ambos = _usuario(c, "ambos@example.com")
        _miembro(c, m.org_a, m.a_admin, "admin", True)
        _miembro(c, m.org_a, m.a_user, "user", True)
        _miembro(c, m.org_b, m.b_admin, "admin", True)
        _miembro(c, m.org_b, m.b_user, "user", True)
        _miembro(c, m.org_a, m.ambos, "user", True)
        _miembro(c, m.org_b, m.ambos, "user", False)

        m.dossier_a = _dossier(c, m.org_a, m.a_admin, "Sujeto A")
        m.carpeta_b = uuid.uuid4()
        m.dossier_b = _dossier(c, m.org_b, m.b_admin, SECRETO_SUJETO, m.carpeta_b)
        m.dossier_b_de_ambos = _dossier(c, m.org_b, m.ambos, SECRETO_SUJETO + "-ambos")

        c.execute(
            text("INSERT INTO dossier_shares (dossier_id, shared_with_user_id, shared_by_user_id) VALUES (:d, :u, :p)"),
            {"d": m.dossier_b, "u": m.b_user, "p": m.b_admin},
        )
        c.execute(
            text("INSERT INTO dossier_alerts (dossier_id, level, title, message) VALUES (:d, 'high', :t, 'x')"),
            {"d": m.dossier_b, "t": SECRETO_ALERTA},
        )
        c.execute(
            text("INSERT INTO dossier_media_mentions (dossier_id, title, url) VALUES (:d, :t, 'https://example.com/n')"),
            {"d": m.dossier_b, "t": SECRETO_PRENSA},
        )
        c.execute(
            text("INSERT INTO dossier_career_entries (dossier_id, company_name, start_date_text) VALUES (:d, :e, '2019')"),
            {"d": m.dossier_b, "e": SECRETO_CARGO},
        )
        m.invitacion_b = uuid.uuid4()
        c.execute(
            text(
                "INSERT INTO org_invites (id, organization_id, email, role, token, status, invited_by_user_id, "
                "created_at, expires_at) VALUES (:i, :o, :e, 'user', :t, 'pending', :p, now(), :x)"
            ),
            {
                "i": m.invitacion_b,
                "o": m.org_b,
                "e": CORREO_INVITADO_B,
                "t": "token-invitacion-b-" + uuid.uuid4().hex[:20],
                "p": m.b_admin,
                "x": datetime.now(UTC) + timedelta(days=7),
            },
        )
        m.token_invitacion_b = c.execute(
            text("SELECT token FROM org_invites WHERE id = :i"), {"i": m.invitacion_b}
        ).scalar_one()

    with Session(pg_vacia) as s:
        trabajos = [
            DossierGenerationJob(organization_id=m.org_a, requested_by_user_id=m.a_admin),
            DossierGenerationJob(organization_id=m.org_b, requested_by_user_id=m.b_admin),
            DossierGenerationJob(organization_id=m.org_b, requested_by_user_id=m.ambos),
        ]
        s.add_all(trabajos)
        s.commit()
        m.job_a, m.job_b, m.job_b_de_ambos = (t.id for t in trabajos)

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    m.a = _cliente(_token(m.a_admin, m.org_a, "admin", "admin@org-a.com"))
    m.b = _cliente(_token(m.b_admin, m.org_b, "admin", CORREO_B_ADMIN))
    try:
        yield m
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)


def _sin_rastro_de_b(m, respuesta) -> None:
    cuerpo = respuesta.text
    prohibidos = [
        str(m.org_b), str(m.dossier_b), str(m.dossier_b_de_ambos), str(m.carpeta_b), str(m.job_b),
        str(m.job_b_de_ambos),
        str(m.b_admin), str(m.b_user), str(m.invitacion_b), m.token_invitacion_b,
        SECRETO_SUJETO, SECRETO_ALERTA, SECRETO_PRENSA, SECRETO_CARGO,
        CORREO_B_ADMIN, CORREO_B_USER, CORREO_INVITADO_B,
    ]
    for valor in prohibidos:
        assert valor not in cuerpo, f"La respuesta a A contiene {valor!r} de la organización B"


# Cada acción de A apunta a un recurso de B. ``{x}`` se reemplaza por los ids del mundo.
ATAQUES = [
    ("GET", "/dossiers/{dossier_b}", None),
    ("GET", "/dossiers/{dossier_b}/shares", None),
    ("GET", "/dossiers/folders/{carpeta_b}", None),
    ("GET", "/dossier-generation-jobs/{job_b}", None),
    ("GET", "/dossier-generation-jobs/{job_b}/stream", None),
    ("POST", "/dossier-generation-jobs/{job_b}/cancel", None),
    ("POST", "/dossiers/{dossier_b}/shares", {"user_id": "{a_user}"}),
    ("DELETE", "/dossiers/{dossier_b}/shares/{b_user}", None),
    ("DELETE", "/dossiers/{dossier_b}", None),
    ("DELETE", "/dossiers/folders/{carpeta_b}", None),
    ("PATCH", "/auth/organization/members/{b_user}", {"role": "viewer"}),
    ("DELETE", "/auth/organization/members/{b_user}", None),
    ("DELETE", "/auth/organization/invites/{invitacion_b}", None),
]


RUTA_INEXISTENTE = {"detail": "Not Found"}


def _rellenar(m, plantilla: str, **reemplazos) -> str:
    valores = {k: str(v) for k, v in vars(m).items() if isinstance(v, uuid.UUID)}
    valores.update(reemplazos)
    return plantilla.format(**valores)


def _ejecutar(m, cliente, metodo, ruta, cuerpo, **reemplazos):
    url = _rellenar(m, ruta, **reemplazos)
    payload = None
    if cuerpo is not None:
        payload = {k: _rellenar(m, v, **reemplazos) if isinstance(v, str) else v for k, v in cuerpo.items()}
    return cliente.request(metodo, url, json=payload)


@pytest.mark.parametrize(("metodo", "ruta", "cuerpo"), ATAQUES, ids=[f"{a} {r}" for a, r, _ in ATAQUES])
def test_el_admin_de_a_no_alcanza_ningun_recurso_de_b(mundo, metodo, ruta, cuerpo):
    antes = _foto_de_b(mundo.engine, mundo.org_b)

    r = _ejecutar(mundo, mundo.a, metodo, ruta, cuerpo)

    assert r.status_code == 404, f"{metodo} {ruta} -> {r.status_code}: {r.text}"
    assert r.json() != RUTA_INEXISTENTE, f"{ruta} no existe: la prueba no estaría probando nada"
    _sin_rastro_de_b(mundo, r)
    assert _foto_de_b(mundo.engine, mundo.org_b) == antes, "Una acción de A cambió datos de B"


@pytest.mark.parametrize(("metodo", "ruta", "cuerpo"), ATAQUES, ids=[f"{a} {r}" for a, r, _ in ATAQUES])
def test_un_id_de_b_responde_igual_que_un_id_inexistente(mundo, metodo, ruta, cuerpo):
    """Sin oráculo de existencia: A no puede distinguir «es de otra empresa» de «no existe»."""
    falso = str(uuid.uuid4())
    inexistente = dict.fromkeys(("dossier_b", "carpeta_b", "job_b", "b_user", "invitacion_b"), falso)

    real = _ejecutar(mundo, mundo.a, metodo, ruta, cuerpo)
    inventado = _ejecutar(mundo, mundo.a, metodo, ruta, cuerpo, **inexistente)

    assert (real.status_code, real.json()) == (inventado.status_code, inventado.json())


LISTADOS = [
    "/dossiers?limit=100",
    "/dossier-generation-jobs?active_only=false&limit=100",
    "/auth/organization/members",
    "/auth/organization/members/manage",
    "/auth/me",
    "/auth/me/organizations",
]


@pytest.mark.parametrize("ruta", LISTADOS)
def test_los_listados_de_a_no_contienen_nada_de_b(mundo, ruta):
    r = mundo.a.get(ruta)
    assert r.status_code == 200, r.text
    _sin_rastro_de_b(mundo, r)


def test_los_listados_de_a_si_contienen_lo_de_a(mundo):
    """Control del caso anterior: el listado no está vacío por otro motivo."""
    assert str(mundo.dossier_a) in mundo.a.get("/dossiers").text
    assert str(mundo.job_a) in mundo.a.get("/dossier-generation-jobs?active_only=false").text
    assert str(mundo.dossier_b) in mundo.b.get("/dossiers").text


def test_quien_pertenece_a_las_dos_solo_ve_la_organizacion_de_su_sesion(mundo):
    """``ambos`` es dueño de un dossier en B, pero con la sesión de A no lo ve."""
    cliente = _cliente(_token(mundo.ambos, mundo.org_a, "user"))

    assert str(mundo.dossier_b_de_ambos) not in cliente.get("/dossiers?limit=100").text
    assert cliente.get(f"/dossiers/{mundo.dossier_b_de_ambos}").status_code == 404

    en_b = _cliente(_token(mundo.ambos, mundo.org_b, "user"))
    assert en_b.get(f"/dossiers/{mundo.dossier_b_de_ambos}").status_code == 200


def test_quien_pertenece_a_las_dos_no_sigue_sus_trabajos_de_b_desde_a(mundo):
    """El trabajo es suyo, pero de la otra organización: con la sesión de A es 404."""
    cliente = _cliente(_token(mundo.ambos, mundo.org_a, "user"))
    job = mundo.job_b_de_ambos

    assert str(job) not in cliente.get("/dossier-generation-jobs?active_only=false").text
    for metodo, ruta in (
        ("GET", f"/dossier-generation-jobs/{job}"),
        ("GET", f"/dossier-generation-jobs/{job}/stream"),
        ("POST", f"/dossier-generation-jobs/{job}/cancel"),
    ):
        assert cliente.request(metodo, ruta).status_code == 404, ruta

    en_b = _cliente(_token(mundo.ambos, mundo.org_b, "user"))
    assert en_b.get(f"/dossier-generation-jobs/{job}").status_code == 200


# --------------------------------------------------------------------------
# El token no da más de lo que dice la base
# --------------------------------------------------------------------------


def test_un_token_con_la_organizacion_de_b_pero_sin_membresia_es_rechazado(mundo):
    """El ``org_id`` del token está firmado, pero igual se verifica la membresía en la base."""
    falso = _cliente(_token(mundo.a_admin, mundo.org_b, "admin"))

    for ruta in ("/dossiers", f"/dossiers/{mundo.dossier_b}", "/auth/organization/members/manage"):
        r = falso.get(ruta)
        assert r.status_code == 403, f"{ruta} -> {r.status_code}"
        _sin_rastro_de_b(mundo, r)


def test_el_rol_admin_del_token_no_vale_si_en_la_base_es_user(mundo):
    """``ambos`` es user en B; un token que diga admin no le abre el dossier ajeno ni la gestión."""
    inflado = _cliente(_token(mundo.ambos, mundo.org_b, "admin"))

    assert inflado.get(f"/dossiers/{mundo.dossier_b}").status_code == 404
    assert inflado.get("/auth/organization/members/manage").status_code == 403
    assert inflado.delete(f"/auth/organization/members/{mundo.b_user}").status_code == 403


def test_al_salir_de_la_organizacion_el_token_vigente_deja_de_servir(mundo):
    viejo = _cliente(_token(mundo.a_user, mundo.org_a, "user"))
    assert viejo.get("/dossiers").status_code == 200

    assert mundo.a.delete(f"/auth/organization/members/{mundo.a_user}").status_code == 204

    assert viejo.get("/dossiers").status_code == 403
    assert viejo.get(f"/dossiers/{mundo.dossier_a}").status_code == 403


# --------------------------------------------------------------------------
# Cambiar de organización, invitaciones y compartir
# --------------------------------------------------------------------------


def test_no_se_puede_cambiar_la_sesion_a_una_organizacion_ajena(mundo):
    r = mundo.a.post("/auth/session/switch", json={"organization_id": str(mundo.org_b)})

    assert r.status_code == 403
    assert "access_token" not in r.text
    assert "set-cookie" not in {k.lower() for k in r.headers}


def test_no_se_puede_aceptar_la_invitacion_de_b_con_otro_correo(mundo):
    antes = _foto_de_b(mundo.engine, mundo.org_b)

    r = mundo.a.post("/auth/organization/invites/accept", json={"token": mundo.token_invitacion_b})

    assert r.status_code == 403
    assert _foto_de_b(mundo.engine, mundo.org_b) == antes


def test_no_se_puede_compartir_un_dossier_de_a_con_alguien_de_b(mundo):
    antes = _foto_de_b(mundo.engine, mundo.org_b)

    r = mundo.a.post(f"/dossiers/{mundo.dossier_a}/shares", json={"user_id": str(mundo.b_user)})

    assert r.status_code == 400
    _sin_rastro_de_b(mundo, r)
    with mundo.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM dossier_shares WHERE dossier_id = :d"), {"d": mundo.dossier_a}).scalar_one() == 0
    assert _foto_de_b(mundo.engine, mundo.org_b) == antes


# --------------------------------------------------------------------------
# Alertas, prensa y trayectoria (S4.5)
# --------------------------------------------------------------------------


def test_una_organizacion_no_accede_a_alertas_ni_prensa_de_otra(mundo):
    """Las tres tablas no tienen ruta propia: solo se alcanzan por su dossier, que ya es 404.

    Si alguien agrega una ruta que las exponga, la segunda parte falla y obliga a sumarla
    a ``ATAQUES``.
    """
    for ruta in (f"/dossiers/{mundo.dossier_b}", f"/dossiers/folders/{mundo.carpeta_b}"):
        r = mundo.a.get(ruta)
        assert r.status_code == 404
        _sin_rastro_de_b(mundo, r)
    _sin_rastro_de_b(mundo, mundo.a.get(f"/dossiers/{mundo.dossier_a}"))

    rutas = " ".join(getattr(r, "path", "") for r in app.routes).lower()
    for palabra in ("alert", "media", "mention", "career", "prensa", "trayectoria"):
        assert palabra not in rutas, f"Hay una ruta nueva con {palabra!r}: agrégala a ATAQUES"


def test_una_organizacion_no_accede_a_dossiers_de_otra(mundo):
    r = mundo.a.get(f"/dossiers/{mundo.dossier_b}")
    assert r.status_code == 404
    _sin_rastro_de_b(mundo, r)


# --------------------------------------------------------------------------
# Auditoría (S4.10) y panel de plataforma
# --------------------------------------------------------------------------


def test_una_organizacion_no_lee_la_auditoria_de_otra(mundo):
    """No hay ruta que lea ``audit_logs``; los intentos de A quedan a nombre de A, no de B."""
    rutas = " ".join(getattr(r, "path", "") for r in app.routes).lower()
    assert "audit" not in rutas and "auditoria" not in rutas

    mundo.b.get(f"/dossiers/{mundo.dossier_b}")
    mundo.a.get(f"/dossiers/{mundo.dossier_b}")

    with mundo.engine.connect() as c:
        filas = c.execute(
            text("SELECT organization_id, user_id, success FROM audit_logs WHERE resource_id = :d ORDER BY created_at"),
            {"d": mundo.dossier_b},
        ).all()
    assert [(f.organization_id, f.user_id, f.success) for f in filas] == [
        (mundo.org_b, mundo.b_admin, True),
        (mundo.org_a, mundo.a_admin, False),
    ]


@pytest.mark.parametrize("ruta", ["/admin/dossiers", "/admin/organizations", "/admin/users", "/admin/overview"])
def test_el_admin_de_una_organizacion_no_usa_el_panel_de_plataforma(mundo, ruta):
    """El panel ``/admin`` ve todas las organizaciones: es solo para administradores de plataforma."""
    r = mundo.a.get(ruta)
    assert r.status_code == 403
    _sin_rastro_de_b(mundo, r)
