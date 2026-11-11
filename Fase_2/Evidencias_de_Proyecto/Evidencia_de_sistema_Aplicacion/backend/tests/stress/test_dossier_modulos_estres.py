"""S5.5 · Estrés de ``modules``: muchos registros o menciones no agrandan la respuesta.

Un dossier de una empresa muy citada puede tener cientos de menciones y registros. El
detalle devuelve como mucho ``MAX_MENCIONES`` y ``MAX_REGISTROS``, deja de recorrer la
entrada al llegar al tope y descarta lo inválido sin costo apreciable.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

from dossier.services.dossier_modules import MAX_MENCIONES, MAX_REGISTROS, modulos_del_dossier
from tests.test_dossier_modulos import fila, registro


def test_diez_mil_filas_de_prensa_se_cortan_en_el_tope_sin_recorrerlas_todas():
    leidas = 0

    def filas():
        nonlocal leidas
        for i in range(10_000):
            leidas += 1
            yield fila(f"T{i}")

    inicio = time.monotonic()
    salida = modulos_del_dossier({}, None, filas())["press_mentions"]
    assert len(salida) == MAX_MENCIONES
    assert leidas == MAX_MENCIONES
    assert time.monotonic() - inicio < 1


def test_miles_de_registros_mezclados_con_basura():
    entrada = [registro(f"Empresa {i}") if i % 3 == 0 else {"record": i} for i in range(5_000)]
    inicio = time.monotonic()
    salida = modulos_del_dossier({"modulos": {"registros_europeos": entrada}}, None, [])["corporate_records"]
    assert len(salida) == MAX_REGISTROS
    assert all("datos_brutos" not in r["record"] for r in salida)
    assert time.monotonic() - inicio < 2


def test_textos_enormes_no_rompen_la_normalizacion():
    enorme = "x" * 200_000
    salida = modulos_del_dossier({}, None, [fila(enorme, summary=enorme, url="https://a.example/" + enorme)])
    assert salida["press_mentions"][0]["headline"] == enorme
    assert SimpleNamespace(**salida)  # serializable como dict plano
