"""BUG-2026-10-19-07: detección de dossiers de calendario con el correo de otro asistente.

Antes de BUG-2026-10-19-02, el dossier de un asistente sin correo propio se guardaba con el
correo de otro asistente del mismo evento. Estas pruebas cubren la detección pura sobre las
filas guardadas (CA1–CA9 de la spec).
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime

from dossier.services.dossiers_correo_ajeno import (
    FilaDossier,
    detectar_afectados,
    fila_desde_dossier,
    marcar_dossier_data,
    nombre_aparece_en_correo,
)

GRUPO = "11111111-1111-1111-1111-111111111111"
OTRO_GRUPO = "22222222-2222-2222-2222-222222222222"


def _fila(dossier_id, nombre, correo, grupo=GRUPO, ya_marcado=False):
    return FilaDossier(
        dossier_id=dossier_id,
        grupo=grupo,
        subject_name=nombre,
        correo=correo,
        ya_marcado=ya_marcado,
    )


def _por_id(afectados):
    return {a.dossier_id: a for a in afectados}


# --- CA1: correo de la primera asistente copiado en el segundo ------------------------


def test_asistente_sin_correo_con_el_de_otra_es_afectado():
    afectados = detectar_afectados(
        [
            _fila("ana", "Ana Pérez", "ana.perez@acme.test"),
            _fila("beto", "Beto Soto", "ana.perez@acme.test"),
        ]
    )

    assert list(_por_id(afectados)) == ["beto"]
    beto = afectados[0]
    assert beto.motivo == "correo_de_otro_asistente"
    assert beto.correo == "ana.perez@acme.test"
    assert beto.presunto_dueno == {"dossier_id": "ana", "subject_name": "Ana Pérez"}
    assert beto.comparte_con == [{"dossier_id": "ana", "subject_name": "Ana Pérez"}]


# --- CA2: la dueña no es necesariamente el primer contacto -----------------------------


def test_duena_por_nombre_aunque_sea_el_segundo_contacto():
    afectados = detectar_afectados(
        [
            _fila("ana", "Ana Pérez", "beto@acme.test"),
            _fila("beto", "Beto Soto", "beto@acme.test"),
        ]
    )

    assert list(_por_id(afectados)) == ["ana"]
    assert afectados[0].presunto_dueno == {"dossier_id": "beto", "subject_name": "Beto Soto"}


# --- CA3: buzón compartido sin dueño identificable -------------------------------------


def test_correo_compartido_sin_dueno_marca_a_todos():
    afectados = detectar_afectados(
        [
            _fila("ana", "Ana Pérez", "ventas@acme.test"),
            _fila("beto", "Beto Soto", "ventas@acme.test"),
        ]
    )

    por_id = _por_id(afectados)
    assert set(por_id) == {"ana", "beto"}
    assert {a.motivo for a in afectados} == {"correo_compartido_sin_dueno"}
    assert all(a.presunto_dueno is None for a in afectados)
    assert por_id["ana"].comparte_con == [{"dossier_id": "beto", "subject_name": "Beto Soto"}]


def test_dos_nombres_que_coinciden_con_el_correo_no_tienen_dueno():
    afectados = detectar_afectados(
        [
            _fila("ana", "Ana Pérez", "ana.soto@acme.test"),
            _fila("beto", "Beto Soto", "ana.soto@acme.test"),
        ]
    )

    assert {a.dossier_id for a in afectados} == {"ana", "beto"}
    assert {a.motivo for a in afectados} == {"correo_compartido_sin_dueno"}


def test_tres_asistentes_con_el_mismo_correo_marca_a_los_dos_ajenos():
    afectados = detectar_afectados(
        [
            _fila("ana", "Ana Pérez", "ana.perez@acme.test"),
            _fila("beto", "Beto Soto", "ana.perez@acme.test"),
            _fila("carla", "Carla Ruiz", "ana.perez@acme.test"),
        ]
    )

    assert {a.dossier_id for a in afectados} == {"beto", "carla"}


# --- CA4 / CA5 / CA6: casos no afectados ----------------------------------------------


def test_cada_asistente_con_su_correo_no_es_afectado():
    assert (
        detectar_afectados(
            [
                _fila("ana", "Ana Pérez", "ana.perez@acme.test"),
                _fila("beto", "Beto Soto", "beto.soto@acme.test"),
            ]
        )
        == []
    )


def test_un_solo_asistente_con_correo_corporativo_del_evento_no_es_afectado():
    assert detectar_afectados([_fila("ana", "Ana Pérez", "ventas@acme.test")]) == []


def test_asistente_con_correo_propio_y_otro_sin_correo_no_es_afectado():
    assert (
        detectar_afectados(
            [
                _fila("ana", "Ana Pérez", "ana.perez@acme.test"),
                _fila("beto", "Beto Soto", None),
            ]
        )
        == []
    )


def test_lista_vacia_no_tiene_afectados():
    assert detectar_afectados([]) == []


# --- CA7: normalización -----------------------------------------------------------------


def test_misma_persona_con_acentos_y_mayusculas_distintas_no_colisiona():
    assert (
        detectar_afectados(
            [
                _fila("a1", "Ana Pérez", "ventas@acme.test"),
                _fila("a2", "  ANA   perez ", "ventas@acme.test"),
            ]
        )
        == []
    )


def test_correo_se_compara_sin_mayusculas_ni_espacios():
    afectados = detectar_afectados(
        [
            _fila("ana", "Ana Pérez", "Ana.Perez@Acme.com"),
            _fila("beto", "Beto Soto", " ana.perez@acme.test "),
        ]
    )

    assert [a.dossier_id for a in afectados] == ["beto"]


# --- CA8: fronteras del grupo -----------------------------------------------------------


def test_mismo_correo_en_grupos_distintos_no_colisiona():
    assert (
        detectar_afectados(
            [
                _fila("ana", "Ana Pérez", "ana.perez@acme.test", grupo=GRUPO),
                _fila("beto", "Beto Soto", "ana.perez@acme.test", grupo=OTRO_GRUPO),
            ]
        )
        == []
    )


def test_filas_sin_grupo_se_ignoran():
    assert (
        detectar_afectados(
            [
                _fila("ana", "Ana Pérez", "ana.perez@acme.test", grupo=None),
                _fila("beto", "Beto Soto", "ana.perez@acme.test", grupo=None),
            ]
        )
        == []
    )


def test_filas_ya_marcadas_se_ignoran():
    assert (
        detectar_afectados(
            [
                _fila("ana", "Ana Pérez", "ana.perez@acme.test"),
                _fila("beto", "Beto Soto", "ana.perez@acme.test", ya_marcado=True),
            ]
        )
        == []
    )


# --- Lectura de la fila guardada --------------------------------------------------------


def test_fila_desde_dossier_usa_carpeta_y_correo_de_respaldo():
    fila = fila_desde_dossier(
        dossier_id="beto",
        dossier_folder_id=None,
        subject_name="Beto Soto",
        subject_email=None,
        dossier_data={
            "calendar_folder": {"id": GRUPO, "title": "Reunión"},
            "person_filters": {"email": "ana.perez@acme.test"},
        },
    )

    assert fila == FilaDossier(
        dossier_id="beto",
        grupo=GRUPO,
        subject_name="Beto Soto",
        correo="ana.perez@acme.test",
        ya_marcado=False,
    )


def test_fila_desde_dossier_prefiere_columnas_y_detecta_marca():
    fila = fila_desde_dossier(
        dossier_id="beto",
        dossier_folder_id=OTRO_GRUPO,
        subject_name="Beto Soto",
        subject_email="beto@acme.test",
        dossier_data={
            "calendar_folder": {"id": GRUPO},
            "person_filters": {"email": "otro@acme.test"},
            "correo_sospechoso": {"tarea": "BUG-2026-10-19-07"},
        },
    )

    assert fila.grupo == OTRO_GRUPO
    assert fila.correo == "beto@acme.test"
    assert fila.ya_marcado is True


def test_fila_desde_dossier_tolera_dossier_data_nulo():
    fila = fila_desde_dossier(
        dossier_id="x",
        dossier_folder_id=None,
        subject_name="Ana",
        subject_email=None,
        dossier_data=None,
    )

    assert fila.grupo is None
    assert fila.correo is None
    assert fila.ya_marcado is False


# --- Coincidencia nombre / correo -------------------------------------------------------


def test_nombre_aparece_en_correo():
    assert nombre_aparece_en_correo("Ana Pérez", "ana.perez@acme.test")
    assert nombre_aparece_en_correo("Juan Pérez", "jperez@acme.test")
    assert nombre_aparece_en_correo("José Núñez", "jose_n@acme.test")
    assert not nombre_aparece_en_correo("Ana Pérez", "ventas@acme.test")
    assert not nombre_aparece_en_correo("Al", "alfredo@acme.test")
    assert not nombre_aparece_en_correo("", "ana@acme.test")
    assert not nombre_aparece_en_correo("Ana", "sin-arroba")


# --- CA9: marca sobre dossier_data ------------------------------------------------------


def test_marcar_dossier_data_agrega_marca_y_anula_correo_sin_mutar_original():
    original = {
        "format": "markdown",
        "body": "# Informe",
        "billing": "charged",
        "calendar_folder": {"id": GRUPO, "title": "Reunión"},
        "person_filters": {"full_name": "Beto Soto", "email": "Ana.Perez@acme.test", "contact_index": 2},
    }
    copia = copy.deepcopy(original)
    afectado = detectar_afectados(
        [
            _fila("ana", "Ana Pérez", "ana.perez@acme.test"),
            _fila("beto", "Beto Soto", "ana.perez@acme.test"),
        ]
    )[0]
    ahora = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)

    nuevo = marcar_dossier_data(original, afectado, correo_anterior="ana.perez@acme.test", ahora=ahora)

    assert original == copia
    assert nuevo["person_filters"]["email"] is None
    assert nuevo["person_filters"]["contact_index"] == 2
    assert nuevo["billing"] == "charged"
    assert nuevo["body"] == "# Informe"
    assert nuevo["correo_sospechoso"] == {
        "tarea": "BUG-2026-10-19-07",
        "motivo": "correo_de_otro_asistente",
        "correo_anterior": "ana.perez@acme.test",
        "person_filters_email_anterior": "Ana.Perez@acme.test",
        "presunto_dueno": {"dossier_id": "ana", "subject_name": "Ana Pérez"},
        "comparte_con": [{"dossier_id": "ana", "subject_name": "Ana Pérez"}],
        "marcado_en": "2026-10-19T12:00:00+00:00",
    }


def test_marcar_dossier_data_conserva_person_filters_email_distinto():
    afectado = detectar_afectados(
        [
            _fila("ana", "Ana Pérez", "ana.perez@acme.test"),
            _fila("beto", "Beto Soto", "ana.perez@acme.test"),
        ]
    )[0]

    nuevo = marcar_dossier_data(
        {"person_filters": {"email": "beto.soto@acme.test"}},
        afectado,
        correo_anterior="ana.perez@acme.test",
        ahora=datetime(2026, 10, 19, tzinfo=UTC),
    )

    assert nuevo["person_filters"]["email"] == "beto.soto@acme.test"
    assert nuevo["correo_sospechoso"]["person_filters_email_anterior"] == "beto.soto@acme.test"
