"""UX-ADMIN-02 · Qué fuentes de prensa usa cada dossier según los ajustes del administrador.

Lógica pura (sin base de datos): la selección según tipo de dossier, profundidad, plan y
cobro, y los valores por defecto de una fuente sin ajustes guardados.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from dossier.news.proveedores import ProveedorNoticias
from dossier.services import news_sources as ns


class Fuente(ProveedorNoticias):
    def __init__(self, clave: str, *, por_defecto: bool = True, configurada: bool = True):
        self.clave = clave
        self.nombre = clave.upper()
        self.activo_por_defecto = por_defecto
        self._configurada = configurada

    def configurado(self) -> bool:
        return self._configurada

    def buscar(self, consulta, *, limite):
        return []


def _instaladas(*fuentes: Fuente) -> dict[str, ProveedorNoticias]:
    return {f.clave: f for f in fuentes}


def _sel(instaladas, ajustes, *, tipo="corporate", profundidad="standard", plan="pro", cobrar=True):
    return ns.seleccionar_fuentes(
        instaladas, ajustes, tipo=tipo, profundidad=profundidad, plan=plan, cobrar=cobrar, contar_uso=True
    )


def test_sin_ajustes_guardados_usa_los_valores_del_adaptador():
    gdelt, premium = Fuente("gdelt"), Fuente("premium", por_defecto=False)
    ajustes = ns.completar_ajustes(_instaladas(gdelt, premium), {})
    assert ajustes["gdelt"].enabled is True
    # Una fuente recién agregada aparece apagada: el admin decide cuándo usarla.
    assert ajustes["premium"].enabled is False
    assert ajustes["gdelt"] == ns.AjusteFuente(
        clave="gdelt",
        enabled=True,
        use_for_corporate=True,
        use_for_person=True,
        min_depth="basic",
        plans=frozenset({"free", "pro", "enterprise"}),
        extra_credits=0,
        max_results=10,
        daily_limit=None,
    )


def test_las_filas_guardadas_mandan_y_se_ignoran_las_de_fuentes_desinstaladas():
    gdelt = Fuente("gdelt")
    guardada = replace(ns.ajuste_por_defecto(gdelt), enabled=False, extra_credits=2)
    huerfana = replace(ns.ajuste_por_defecto(Fuente("vieja")), clave="vieja")
    ajustes = ns.completar_ajustes(_instaladas(gdelt), {"gdelt": guardada, "vieja": huerfana})
    assert list(ajustes) == ["gdelt"]
    assert ajustes["gdelt"].enabled is False and ajustes["gdelt"].extra_credits == 2


def test_selecciona_solo_activas_configuradas_y_del_plan():
    a, b, c, d = Fuente("activa"), Fuente("apagada"), Fuente("sin_clave", configurada=False), Fuente("solo_ent")
    inst = _instaladas(a, b, c, d)
    ajustes = ns.completar_ajustes(inst, {})
    ajustes["apagada"] = replace(ajustes["apagada"], enabled=False)
    ajustes["solo_ent"] = replace(ajustes["solo_ent"], plans=frozenset({"enterprise"}))
    assert [f.proveedor.clave for f in _sel(inst, ajustes, plan="pro")] == ["activa"]
    assert [f.proveedor.clave for f in _sel(inst, ajustes, plan="enterprise")] == ["activa", "solo_ent"]


@pytest.mark.parametrize(
    ("minima", "profundidad", "entra"),
    [
        ("basic", "basic", True),
        ("standard", "basic", False),
        ("standard", "standard", True),
        ("standard", "deep", True),
        ("deep", "standard", False),
    ],
)
def test_profundidad_minima_en_empresas(minima, profundidad, entra):
    premium = Fuente("premium")
    inst = _instaladas(premium)
    ajustes = {"premium": replace(ns.ajuste_por_defecto(premium), min_depth=minima)}
    assert bool(_sel(inst, ajustes, profundidad=profundidad)) is entra


def test_en_personas_la_profundidad_no_aplica_pero_si_el_interruptor():
    premium = Fuente("premium")
    inst = _instaladas(premium)
    base = replace(ns.ajuste_por_defecto(premium), min_depth="deep")
    assert _sel(inst, {"premium": base}, tipo="person", profundidad="basic")
    sin_personas = replace(base, use_for_person=False)
    assert _sel(inst, {"premium": sin_personas}, tipo="person") == []
    sin_empresas = replace(base, use_for_corporate=False, min_depth="basic")
    assert _sel(inst, {"premium": sin_empresas}, tipo="corporate") == []


def test_lleva_limites_y_creditos_extra_solo_si_se_cobra():
    premium = Fuente("premium")
    inst = _instaladas(premium)
    ajustes = {"premium": replace(ns.ajuste_por_defecto(premium), extra_credits=3, max_results=25, daily_limit=40)}
    (con_cobro,) = _sel(inst, ajustes, cobrar=True)
    assert (con_cobro.limite, con_cobro.creditos_extra, con_cobro.limite_diario, con_cobro.contar_uso) == (
        25,
        3,
        40,
        True,
    )
    (sin_cobro,) = _sel(inst, ajustes, cobrar=False)
    assert sin_cobro.creditos_extra == 0
    assert ns.creditos_extra_maximos([con_cobro]) == 3
    assert ns.creditos_extra_maximos([]) == 0


def test_plan_desconocido_se_trata_como_free():
    solo_pro = Fuente("solo_pro")
    inst = _instaladas(solo_pro)
    ajustes = {"solo_pro": replace(ns.ajuste_por_defecto(solo_pro), plans=frozenset({"pro"}))}
    assert _sel(inst, ajustes, plan=None) == []
    assert _sel(inst, ajustes, plan="raro") == []
