"""UX-ADMIN-02 · Fuentes de noticias administrables, con cobro extra y prensa en personas (Postgres).

Flujo completo con el worker y el trigger de cobro reales. Solo los proveedores externos son
dobles: la fuente GDELT responde lo que diga la prueba, sin red. Requiere ``TEST_DATABASE_URL``.
"""
# ruff: noqa: F811 (el fixture «mundo» se importa de las pruebas de S7.3)
from __future__ import annotations

import threading
from uuid import UUID

import pytest
from sqlalchemy import text

from dossier.news import agent as agente_noticias
from dossier.news.client import ProveedorNoticiasError
from dossier.news.proveedores import ArticuloNoticia, registro
from tests.integration.test_s7_3_creditos_aislamiento import (  # noqa: F401
    SALDO_INICIAL,
    cliente,
    dossiers,
    encolar_reunion,
    movimientos,
    mundo,
    pedir_persona,
    procesar,
    saldo,
)

RUTA_ADMIN = "/admin/news-sources"


@pytest.fixture
def admin(mundo):
    with mundo.engine.begin() as c:
        c.execute(text("UPDATE users SET is_platform_admin = true WHERE id = :u"), {"u": mundo.a_admin})
    return cliente(mundo.a_admin, mundo.org_a)


@pytest.fixture
def prensa_real(mundo, monkeypatch):
    """Recolector real; GDELT responde lo que diga la prueba y NewsAPI queda sin clave."""
    monkeypatch.setattr("dossier.news.agent.collect_press_mentions", REAL_COLLECT)
    monkeypatch.delenv("NEWS_API_KEY", raising=False)
    gdelt = registro.proveedores_instalados()["gdelt_news"]
    estado = {"articulos": [], "error": None, "consultas": []}

    def buscar(consulta, *, limite):
        estado["consultas"].append(consulta)
        if estado["error"]:
            raise estado["error"]
        return list(estado["articulos"])

    monkeypatch.setattr(gdelt, "buscar", buscar)
    return estado


REAL_COLLECT = agente_noticias.collect_press_mentions


def _articulo(titulo: str, url: str = "https://diario.example/nota-1") -> ArticuloNoticia:
    return ArticuloNoticia(
        titulo=titulo, url=url, medio="Diario Ejemplo", publicado="2026-11-01T10:00:00Z", resumen=titulo
    )


def _ajustar(admin, clave: str, **cambios):
    resp = admin.patch(f"{RUTA_ADMIN}/{clave}", json=cambios)
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- Panel de administración --------------------------------------------------------------


def test_lista_las_fuentes_instaladas_con_sus_valores(admin, monkeypatch):
    monkeypatch.delenv("NEWS_API_KEY", raising=False)
    resp = admin.get(RUTA_ADMIN)
    assert resp.status_code == 200
    fuentes = {f["key"]: f for f in resp.json()["sources"]}
    assert {"gdelt_news", "news_api"} <= set(fuentes)
    gdelt, newsapi = fuentes["gdelt_news"], fuentes["news_api"]
    assert gdelt["configured"] is True and gdelt["key_env_var"] is None
    assert newsapi["configured"] is False and newsapi["key_env_var"] == "NEWS_API_KEY"
    assert gdelt["enabled"] is True and gdelt["plans"] == ["free", "pro", "enterprise"]
    assert gdelt["extra_credits"] == 0 and gdelt["daily_limit"] is None and gdelt["used_today"] == 0
    # Nunca se expone el valor de una clave.
    monkeypatch.setenv("NEWS_API_KEY", "secreto-que-no-debe-salir")
    assert "secreto-que-no-debe-salir" not in admin.get(RUTA_ADMIN).text


def test_solo_el_admin_de_plataforma(mundo):
    comun = cliente(mundo.b_admin, mundo.org_b)
    assert comun.get(RUTA_ADMIN).status_code == 403
    assert comun.patch(f"{RUTA_ADMIN}/gdelt_news", json={"enabled": False}).status_code == 403


def test_cambiar_ajustes_persiste_y_queda_en_auditoria(admin, mundo):
    nuevo = _ajustar(
        admin,
        "gdelt_news",
        enabled=True,
        use_for_person=False,
        min_depth="standard",
        plans=["pro", "enterprise"],
        extra_credits=2,
        max_results=20,
        daily_limit=50,
    )
    assert (nuevo["min_depth"], nuevo["plans"], nuevo["extra_credits"], nuevo["daily_limit"]) == (
        "standard",
        ["pro", "enterprise"],
        2,
        50,
    )
    assert nuevo["updated_by_email"] == "admin@a.com"
    otra_vez = {f["key"]: f for f in admin.get(RUTA_ADMIN).json()["sources"]}["gdelt_news"]
    assert otra_vez["use_for_person"] is False and otra_vez["max_results"] == 20

    # null quita el límite diario; un campo ausente no cambia.
    assert _ajustar(admin, "gdelt_news", daily_limit=None)["daily_limit"] is None
    with mundo.engine.connect() as c:
        auditoria = c.execute(
            text("SELECT request_data FROM audit_logs WHERE action = 'ADMIN news_source_settings' ORDER BY created_at")
        ).scalars().all()
    assert len(auditoria) == 2
    assert auditoria[0]["source"] == "gdelt_news"
    assert auditoria[0]["cambios"]["extra_credits"] == {"antes": 0, "despues": 2}
    assert auditoria[1]["cambios"] == {"daily_limit": {"antes": 50, "despues": None}}


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"enabled": "true"},
        {"extra_credits": 21},
        {"extra_credits": -1},
        {"max_results": 0},
        {"daily_limit": 0},
        {"min_depth": "maxima"},
        {"plans": []},
        {"plans": ["gold"]},
        {"api_key": "no-se-guarda-aqui"},
    ],
)
def test_rechaza_valores_invalidos(admin, cuerpo):
    assert admin.patch(f"{RUTA_ADMIN}/gdelt_news", json=cuerpo).status_code == 422


def test_fuente_desconocida_es_404(admin):
    assert admin.patch(f"{RUTA_ADMIN}/no_existe", json={"enabled": True}).status_code == 404


def test_el_limite_diario_no_se_pasa_con_pedidos_simultaneos(admin, mundo):
    from dossier.services.news_sources import reservar_consulta

    resultados: list[bool] = []
    barrera = threading.Barrier(8)

    def pedir():
        barrera.wait()
        resultados.append(reservar_consulta("gdelt_news", 3, mundo.engine))

    hilos = [threading.Thread(target=pedir) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(resultados) == [False] * 5 + [True] * 3
    gdelt = {f["key"]: f for f in admin.get(RUTA_ADMIN).json()["sources"]}["gdelt_news"]
    assert gdelt["used_today"] == 3


# --- Estimación para la pantalla --------------------------------------------------------


def test_estimacion_de_fuentes_y_creditos_extra(admin, mundo):
    _ajustar(admin, "gdelt_news", extra_credits=2, min_depth="standard")
    usuario = cliente(mundo.a_admin, mundo.org_a)
    basica = usuario.get("/news-sources/applicable", params={"kind": "corporate", "depth": "basic"}).json()
    estandar = usuario.get("/news-sources/applicable", params={"kind": "corporate", "depth": "standard"}).json()
    persona = usuario.get("/news-sources/applicable", params={"kind": "person"}).json()
    assert basica["extra_credits"] == 0 and basica["sources"] == []
    assert estandar["extra_credits"] == 2
    assert [s["key"] for s in estandar["sources"]] == ["gdelt_news"]
    assert persona["extra_credits"] == 2
    assert usuario.get("/news-sources/applicable", params={"kind": "otra"}).status_code == 422


# --- Cobro extra en empresas --------------------------------------------------------------


def _empresa(mundo, depth: str = "basic"):
    return cliente(mundo.a_admin, mundo.org_a).post(
        "/dossiers/corporate/generate", json={"subject_query": "Acme Corp", "depth": depth}
    )


def test_empresa_cobra_el_extra_de_la_fuente_que_respondio(admin, mundo, prensa_real):
    _ajustar(admin, "gdelt_news", extra_credits=2)
    prensa_real["articulos"] = [_articulo("Acme Corp abre oficina en Santiago")]
    resp = _empresa(mundo)
    assert resp.status_code == 200, resp.text
    assert resp.json()["credits_consumed"] == 1 + 2
    (d,) = dossiers(mundo, mundo.org_a)
    assert d.credits_consumed == 3
    assert movimientos(mundo, mundo.org_a) == [(d.id, -3, SALDO_INICIAL - 3)]
    detalle = cliente(mundo.a_admin, mundo.org_a).get(f"/dossiers/{d.id}").json()
    assert [m["headline"] for m in detalle["modules"]["press_mentions"]] == ["Acme Corp abre oficina en Santiago"]


def test_si_la_fuente_falla_no_cobra_su_extra(admin, mundo, prensa_real):
    _ajustar(admin, "gdelt_news", extra_credits=2)
    prensa_real["error"] = ProveedorNoticiasError("HTTP 503")
    assert _empresa(mundo).json()["credits_consumed"] == 1
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL - 1


def test_fuente_fuera_de_su_profundidad_no_se_consulta(admin, mundo, prensa_real):
    _ajustar(admin, "gdelt_news", extra_credits=2, min_depth="deep")
    assert _empresa(mundo, "basic").json()["credits_consumed"] == 1
    assert prensa_real["consultas"] == []


def test_sin_saldo_para_el_extra_no_empieza(admin, mundo, prensa_real):
    _ajustar(admin, "gdelt_news", extra_credits=5)
    with mundo.engine.begin() as c:
        c.execute(text("UPDATE organizations SET credits_balance = 3 WHERE id = :o"), {"o": mundo.org_a})
    resp = _empresa(mundo)
    assert resp.status_code == 402
    assert prensa_real["consultas"] == []
    assert dossiers(mundo, mundo.org_a) == []


def test_empresa_por_la_cola_estima_y_cobra_el_extra(admin, mundo, prensa_real):
    _ajustar(admin, "gdelt_news", extra_credits=2)
    prensa_real["articulos"] = [_articulo("Acme Corp abre oficina en Santiago")]
    resp = cliente(mundo.a_admin, mundo.org_a).post(
        "/dossiers/corporate/generate", json={"subject_query": "Acme Corp", "depth": "basic", "async_mode": True}
    )
    assert resp.json()["credits_estimated"] == 3
    mundo.jobs.append(resp.json()["job_id"])
    job = procesar(mundo, resp.json()["job_id"])
    assert job["status"] == "completed" and job["credits_consumed"] == 3


def test_limite_diario_agotado_omite_la_fuente_sin_cobrar(admin, mundo, prensa_real):
    _ajustar(admin, "gdelt_news", extra_credits=2, daily_limit=1)
    prensa_real["articulos"] = [_articulo("Acme Corp abre oficina en Santiago")]
    assert _empresa(mundo).json()["credits_consumed"] == 3
    segundo = cliente(mundo.a_admin, mundo.org_a).post(
        "/dossiers/corporate/generate", json={"subject_query": "Globex Corp", "depth": "basic"}
    )
    assert segundo.json()["credits_consumed"] == 1
    assert len(prensa_real["consultas"]) == 1


def test_el_trigger_ignora_un_extra_que_no_es_un_numero(mundo):
    with mundo.engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO dossiers (organization_id, requested_by_user_id, subject_name, depth_level, status, "
                "dossier_data) VALUES (:o, :u, 'X', 'basic', 'complete', "
                "'{\"billing\": \"charged\", \"news_extra_credits\": \"-50; DROP\"}'::jsonb)"
            ),
            {"o": mundo.org_a, "u": mundo.a_admin},
        )
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL - 1


# --- Prensa en personas -------------------------------------------------------------------


def test_persona_busca_prensa_cobra_el_extra_y_muestra_la_tarjeta(admin, mundo, prensa_real):
    _ajustar(admin, "gdelt_news", extra_credits=1)
    prensa_real["articulos"] = [
        _articulo("Ana Prueba, de Empresa de Prueba SA, lidera la expansión", "https://diario.example/ana"),
        _articulo("Otra Ana Prueba gana un torneo de ajedrez", "https://diario.example/otra"),
    ]
    job = procesar(mundo, pedir_persona(mundo, mundo.a_admin, mundo.org_a))
    assert job["status"] == "completed"
    (scope,) = job["progress"]["scopes"]
    etapas = {e["stage_id"]: e for e in scope["stages"]}
    assert etapas["person.press_search"]["status"] == "completed"

    # Nombre exacto entre comillas y la empresa que encontró PDL, sin la forma jurídica.
    (consulta,) = prensa_real["consultas"]
    assert consulta == '"Ana Prueba" "Empresa de Prueba"'

    (d,) = dossiers(mundo, mundo.org_a)
    assert d.credits_consumed == 1 + 1 == job["credits_consumed"]
    detalle = cliente(mundo.a_admin, mundo.org_a).get(f"/dossiers/{d.id}").json()
    # El homónimo sin la empresa se descarta.
    assert [m["headline"] for m in detalle["modules"]["press_mentions"]] == [
        "Ana Prueba, de Empresa de Prueba SA, lidera la expansión"
    ]
    # La IA recibe las menciones como datos externos.
    prompt = mundo.llm.llamadas[0]["prompt"]
    assert "lidera la expansión" in prompt and "ajedrez" not in prompt


def test_persona_sin_fuentes_para_personas_omite_la_etapa(admin, mundo, prensa_real):
    _ajustar(admin, "gdelt_news", use_for_person=False, extra_credits=3)
    job = procesar(mundo, pedir_persona(mundo, mundo.a_admin, mundo.org_a))
    (scope,) = job["progress"]["scopes"]
    etapa = next(e for e in scope["stages"] if e["stage_id"] == "person.press_search")
    assert (etapa["status"], etapa["reason_code"]) == ("skipped", "feature_disabled")
    assert job["credits_consumed"] == 1
    assert prensa_real["consultas"] == []


def test_persona_con_la_prensa_caida_igual_sale_y_no_cobra_el_extra(admin, mundo, prensa_real):
    _ajustar(admin, "gdelt_news", extra_credits=2)
    prensa_real["error"] = ProveedorNoticiasError("HTTP 500")
    job = procesar(mundo, pedir_persona(mundo, mundo.a_admin, mundo.org_a))
    assert job["status"] == "completed" and job["credits_consumed"] == 1
    (scope,) = job["progress"]["scopes"]
    etapa = next(e for e in scope["stages"] if e["stage_id"] == "person.press_search")
    assert etapa["status"] == "failed"


def test_persona_con_la_prensa_limitada_muestra_el_motivo(admin, mundo, prensa_real):
    from dossier.news.client import LimiteProveedorNoticias

    prensa_real["error"] = LimiteProveedorNoticias("HTTP 429")
    job = procesar(mundo, pedir_persona(mundo, mundo.a_admin, mundo.org_a))
    (scope,) = job["progress"]["scopes"]
    etapa = next(e for e in scope["stages"] if e["stage_id"] == "person.press_search")
    assert (etapa["status"], etapa["reason_code"]) == ("failed", "provider_rate_limit")
    assert job["status"] == "completed"


def test_empresa_con_la_prensa_limitada_muestra_el_motivo(admin, mundo, prensa_real):
    from dossier.news.client import LimiteProveedorNoticias

    prensa_real["error"] = LimiteProveedorNoticias("HTTP 429")
    resp = cliente(mundo.a_admin, mundo.org_a).post(
        "/dossiers/corporate/generate", json={"subject_query": "Acme Corp", "depth": "basic", "async_mode": True}
    )
    mundo.jobs.append(resp.json()["job_id"])
    job = procesar(mundo, resp.json()["job_id"])
    (scope,) = job["progress"]["scopes"]
    prensa = next(a for a in scope["agents"] if a["agent_name"] == "agent_news")
    assert (prensa["status"], prensa["reason_code"]) == ("failed", "provider_rate_limit")


def test_persona_estima_el_extra_al_encolar(admin, mundo):
    _ajustar(admin, "gdelt_news", extra_credits=2)
    resp = cliente(mundo.a_admin, mundo.org_a).post(
        "/dossiers/person/research",
        json={"full_name": "Ana Prueba", "research_source": "pdl", "async_mode": True},
    )
    assert resp.json()["credits_estimated"] == 3
    mundo.jobs.append(resp.json()["job_id"])


# --- Calendario ---------------------------------------------------------------------------


def test_calendario_cobra_lo_mismo_que_suman_sus_dossiers(admin, mundo, prensa_real):
    _ajustar(admin, "gdelt_news", extra_credits=1)
    prensa_real["articulos"] = [_articulo("Nota sin relación")]
    job = procesar(mundo, encolar_reunion(mundo, mundo.a_admin, mundo.org_a))
    assert job["status"] == "completed"
    filas = dossiers(mundo, mundo.org_a)
    assert filas
    total = sum(f.credits_consumed for f in filas)
    assert job["credits_consumed"] == total
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL - total
    # Cada dossier que consultó la prensa pagó su extra (1) sobre su costo base.
    assert all(f.credits_consumed in (1 + 1, 3 + 1) for f in filas), [(f.subject_name, f.credits_consumed, f.status) for f in filas]
    assert {UUID(str(m[0])) for m in movimientos(mundo, mundo.org_a)} == {f.id for f in filas}
