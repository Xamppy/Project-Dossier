"""S4.10 · Registro de auditoría: funciones puras (pruebas unitarias).

Diseño de campos: db/Migracion.md, sección 13 (WHO, WHAT, WHEN, WHERE, RESULT).
El flujo contra Postgres está en ``tests/integration/test_audit_log_flujo.py``.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from dossier.api import audit_middleware as am
from dossier.security.jwt_tokens import create_access_token
from dossier.services import audit_log as al

AHORA = datetime(2026, 11, 2, 12, 30, 15, 123456, tzinfo=UTC)


def _campos(**cambios) -> dict:
    base = {
        "action": "GET /dossiers/{dossier_id}",
        "resource_type": "dossier",
        "resource_id": uuid.UUID("11111111-1111-4111-8111-111111111111"),
        "user_role_at_time": "admin",
        "created_at": AHORA,
        "ip_address": "127.0.0.1",
        "user_agent": "pytest",
        "http_status": 200,
        "success": True,
        "error_message": None,
        "request_data": {"query": {"limit": "5"}},
        "duration_ms": 12,
    }
    return {**base, **cambios}


# --------------------------------------------------------------------------
# Datos personales fuera del registro
# --------------------------------------------------------------------------


def test_redactar_oculta_datos_personales_en_cualquier_nivel():
    crudo = {
        "limit": "5",
        "email": "ana@empresa.cl",
        "filtro": {"full_name": "Ana Prueba", "phone": "+56 9", "estado": "complete"},
        "lista": [{"linkedin_url": "https://linkedin.com/in/ana"}],
        "password": "secreta",
        "access_token": "eyJ...",
    }

    limpio = al.redact(crudo)

    assert limpio["limit"] == "5"
    assert limpio["filtro"]["estado"] == "complete"
    for valor in (limpio["email"], limpio["filtro"]["full_name"], limpio["filtro"]["phone"],
                  limpio["lista"][0]["linkedin_url"], limpio["password"], limpio["access_token"]):
        assert valor == al.REDACTED
    assert "ana@empresa.cl" not in str(limpio)


def test_redactar_acorta_textos_largos_y_tolera_vacios():
    assert al.redact(None) is None
    assert al.redact({}) == {}
    assert len(al.redact({"q": "x" * 5000})["q"]) <= al.MAX_VALUE_CHARS + 1


def test_redactar_no_modifica_el_original():
    crudo = {"email": "a@b.cl"}
    al.redact(crudo)
    assert crudo == {"email": "a@b.cl"}


# --------------------------------------------------------------------------
# Firma del registro (log_hash)
# --------------------------------------------------------------------------


def test_la_firma_es_estable_y_de_64_caracteres():
    assert al.compute_log_hash(_campos()) == al.compute_log_hash(_campos())
    assert len(al.compute_log_hash(_campos())) == 64


@pytest.mark.parametrize(
    "cambio",
    [
        {"action": "DELETE /dossiers/{dossier_id}"},
        {"resource_id": uuid.uuid4()},
        {"user_role_at_time": "viewer"},
        {"created_at": AHORA.replace(microsecond=0)},
        {"ip_address": "10.0.0.1"},
        {"http_status": 403},
        {"success": False},
        {"request_data": {"query": {"limit": "6"}}},
        {"duration_ms": 13},
    ],
)
def test_alterar_cualquier_campo_firmado_cambia_la_firma(cambio):
    assert al.compute_log_hash(_campos(**cambio)) != al.compute_log_hash(_campos())


def test_la_firma_usa_una_clave_secreta(monkeypatch):
    """Sin la clave no se puede recalcular la firma de un registro alterado."""
    original = al.compute_log_hash(_campos())
    monkeypatch.setenv("AUDIT_LOG_HMAC_KEY", "otra-clave-distinta-para-la-prueba")
    assert al.compute_log_hash(_campos()) != original


def test_verificar_la_firma_detecta_un_registro_alterado():
    fila = _campos()
    fila["log_hash"] = al.compute_log_hash(fila)
    assert al.verify_log_hash(fila) is True

    fila["http_status"] = 200 if fila["http_status"] != 200 else 500
    assert al.verify_log_hash(fila) is False


def test_la_firma_no_depende_del_usuario_ni_la_organizacion():
    """Al borrar un usuario la base deja su id en NULL (derecho al olvido); la firma sigue valiendo."""
    con_ids = _campos(user_id=uuid.uuid4(), organization_id=uuid.uuid4())
    sin_ids = _campos(user_id=None, organization_id=None)
    assert al.compute_log_hash(con_ids) == al.compute_log_hash(sin_ids)


# --------------------------------------------------------------------------
# Qué rutas se auditan
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metodo", "plantilla", "tipo", "param"),
    [
        ("GET", "/dossiers", "dossier", None),
        ("GET", "/dossiers/{dossier_id}", "dossier", "dossier_id"),
        ("DELETE", "/dossiers/{dossier_id}", "dossier", "dossier_id"),
        ("GET", "/dossiers/folders/{folder_id}", "dossier_folder", "folder_id"),
        ("POST", "/dossiers/corporate/generate", "dossier", None),
        ("POST", "/dossiers/person/research", "dossier", None),
        ("POST", "/calendario/generar-dossiers-google", "dossier", None),
        ("GET", "/dossier-generation-jobs/{job_id}", "dossier_generation_job", "job_id"),
        ("GET", "/admin/dossiers", "dossier", None),
    ],
)
def test_rutas_de_dossiers_se_auditan(metodo, plantilla, tipo, param):
    regla = am.audit_rule(metodo, plantilla)
    assert regla is not None
    assert (regla.resource_type, regla.id_param) == (tipo, param)


@pytest.mark.parametrize(
    ("metodo", "plantilla"),
    [("GET", "/auth/me"), ("POST", "/auth/login"), ("GET", "/health"), ("OPTIONS", "/dossiers"), ("GET", None)],
)
def test_otras_rutas_no_se_auditan(metodo, plantilla):
    assert am.audit_rule(metodo, plantilla) is None


# --------------------------------------------------------------------------
# Actor y recurso
# --------------------------------------------------------------------------


def test_el_actor_sale_del_token_sin_consultar_la_base():
    u, o = uuid.uuid4(), uuid.uuid4()
    token = create_access_token(user_id=str(u), email="a@b.cl", organization_id=str(o), role="viewer")

    actor = am.actor_from_authorization(f"Bearer {token}")

    assert (actor.user_id, actor.organization_id, actor.role) == (u, o, "viewer")


@pytest.mark.parametrize("cabecera", [None, "", "Basic abc", "Bearer basura", "Bearer "])
def test_sin_token_valido_el_actor_es_anonimo(cabecera):
    actor = am.actor_from_authorization(cabecera)
    assert (actor.user_id, actor.organization_id, actor.role) == (None, None, None)


@pytest.mark.parametrize(
    ("cuerpo", "esperado"),
    [
        ({"id": "11111111-1111-4111-8111-111111111111"}, "11111111-1111-4111-8111-111111111111"),
        ({"dossier_id": "22222222-2222-4222-8222-222222222222"}, "22222222-2222-4222-8222-222222222222"),
        ({"saved_dossier": {"id": "33333333-3333-4333-8333-333333333333"}}, "33333333-3333-4333-8333-333333333333"),
        ({"job": {"id": "44444444-4444-4444-8444-444444444444"}}, "44444444-4444-4444-8444-444444444444"),
        ({"id": "no-es-uuid"}, None),
        ([1, 2], None),
        (None, None),
    ],
)
def test_id_del_recurso_desde_la_respuesta(cuerpo, esperado):
    resultado = am.resource_id_from_body(cuerpo)
    assert (str(resultado) if resultado else None) == esperado


def test_ids_de_dossiers_guardados_sin_la_carpeta():
    guardados = {
        "corporate": {"id": "a"},
        "person": {"id": "b"},
        "persons": [{"id": "b"}, {"id": "c"}],
        "folder": {"id": "carpeta"},
    }
    assert al.saved_dossier_ids(guardados) == ["a", "b", "c"]
    assert al.saved_dossier_ids(None) == []
