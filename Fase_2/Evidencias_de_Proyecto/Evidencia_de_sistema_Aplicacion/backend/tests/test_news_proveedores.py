"""UX-ADMIN-02 · Fuentes de noticias enchufables: registro, contrato y recolector.

Cada fuente es un adaptador en ``dossier/news/proveedores/``. El registro los descubre solo,
omite los inválidos sin romper el arranque, y el recolector consulta solo las fuentes que le
pasan (o las activas por defecto con su clave configurada).
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from dossier.news import agent
from dossier.news.client import ProveedorNoticiasError
from dossier.news.proveedores import ArticuloNoticia, ProveedorNoticias, registro
from dossier.schemas.dossier_executive_payload import SourceType

# --- Registro --------------------------------------------------------------------------


def test_el_registro_trae_gdelt_y_newsapi_y_no_la_plantilla():
    instalados = registro.proveedores_instalados()
    assert {"gdelt_news", "news_api"} <= set(instalados)
    assert all(not clave.startswith("_") for clave in instalados)
    assert "plantilla" not in " ".join(instalados)


def test_gdelt_es_gratis_y_newsapi_pide_su_variable():
    instalados = registro.proveedores_instalados()
    assert instalados["gdelt_news"].variable_clave is None
    assert instalados["news_api"].variable_clave == "NEWS_API_KEY"
    assert instalados["gdelt_news"].activo_por_defecto is True


def _paquete(tmp_path, monkeypatch, modulos: dict[str, str]) -> str:
    nombre = "fuentes_de_prueba"
    carpeta = tmp_path / nombre
    carpeta.mkdir()
    (carpeta / "__init__.py").write_text("", encoding="utf-8")
    for archivo, codigo in modulos.items():
        (carpeta / f"{archivo}.py").write_text(textwrap.dedent(codigo), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    for clave in [k for k in sys.modules if k.startswith(nombre)]:
        monkeypatch.delitem(sys.modules, clave)
    return nombre


_VALIDO = """
from dossier.news.proveedores import ProveedorNoticias

class Fuente(ProveedorNoticias):
    clave = "{clave}"
    nombre = "Fuente {clave}"

    def buscar(self, consulta, *, limite):
        return []

PROVEEDOR = Fuente()
"""


def test_descubre_validos_y_omite_rotos_repetidos_y_privados(tmp_path, monkeypatch, caplog):
    paquete = _paquete(
        tmp_path,
        monkeypatch,
        {
            "buena": _VALIDO.format(clave="buena"),
            "repetida": _VALIDO.format(clave="buena"),
            "clave_mala": _VALIDO.format(clave="Con Espacios"),
            "rota": "raise ImportError('falta una librería')",
            "sin_proveedor": "X = 1",
            "_privada": _VALIDO.format(clave="privada"),
        },
    )
    encontrados = registro.descubrir_proveedores(paquete)
    assert list(encontrados) == ["buena"]
    assert "rota" in caplog.text
    assert "Con Espacios" in caplog.text


@pytest.mark.parametrize(
    ("cambios", "motivo"),
    [
        ({"clave": "a"}, "clave"),
        ({"clave": "1fuente"}, "clave"),
        ({"nombre": "  "}, "nombre"),
        ({"variable_clave": "news-api-key"}, "variable"),
    ],
)
def test_validar_proveedor_explica_que_falla(cambios, motivo):
    class Fuente(ProveedorNoticias):
        clave = "valida"
        nombre = "Válida"

        def buscar(self, consulta, *, limite):
            return []

    for atributo, valor in cambios.items():
        setattr(Fuente, atributo, valor)
    problema = registro.validar_proveedor(Fuente())
    assert problema is not None and motivo in problema


def test_validar_rechaza_lo_que_no_es_un_proveedor():
    assert registro.validar_proveedor(object()) is not None


# --- Contrato: lo cumple cualquier adaptador instalado -----------------------------------


@pytest.fixture(params=sorted(registro.proveedores_instalados()))
def proveedor(request, monkeypatch) -> ProveedorNoticias:
    prov = registro.proveedores_instalados()[request.param]
    if prov.variable_clave:
        monkeypatch.setenv(prov.variable_clave, "clave-de-prueba")
    return prov


def test_contrato_datos_validos(proveedor):
    assert registro.validar_proveedor(proveedor) is None
    assert isinstance(proveedor.tipo_fuente, SourceType)
    assert proveedor.configurado() is True


def test_contrato_consulta_vacia_no_sale_a_la_red(proveedor):
    assert proveedor.buscar("   ", limite=5) == []


def test_contrato_un_fallo_http_se_informa_como_error_del_proveedor(proveedor, monkeypatch):
    import requests

    def caida(*_a, **_k):
        raise requests.ConnectionError("sin conexión")

    monkeypatch.setattr(requests, "get", caida)
    monkeypatch.setattr(requests, "post", caida)
    with pytest.raises(ProveedorNoticiasError):
        proveedor.buscar('"Ana Pérez"', limite=5)


def test_sin_su_variable_no_esta_configurado(monkeypatch):
    newsapi = registro.proveedores_instalados()["news_api"]
    monkeypatch.delenv("NEWS_API_KEY", raising=False)
    assert newsapi.configurado() is False


# --- Recolector con fuentes explícitas ---------------------------------------------------


class Falsa(ProveedorNoticias):
    nombre = "Falsa"

    def __init__(self, clave: str, articulos=None, error: Exception | None = None):
        self.clave = clave
        self.nombre = f"Fuente {clave}"
        self._articulos = articulos or []
        self._error = error
        self.llamadas: list[tuple[str, int]] = []

    def buscar(self, consulta, *, limite):
        self.llamadas.append((consulta, limite))
        if self._error:
            raise self._error
        return list(self._articulos)


def _art(titulo: str, url: str, medio: str = "Diario") -> ArticuloNoticia:
    return ArticuloNoticia(titulo=titulo, url=url, medio=medio, publicado="2026-11-01T10:00:00Z", resumen="Nota.")


def test_consulta_solo_las_fuentes_recibidas_con_su_limite():
    a = Falsa("fuente_a", [_art("Acme crece", "https://a.example/1")])
    b = Falsa("fuente_b", [_art("Acme invierte", "https://b.example/2")])
    resultado = agent.collect_press_mentions(
        "Acme", fuentes=[agent.FuentePrensa(a, limite=3), agent.FuentePrensa(b, limite=7)]
    )
    assert a.llamadas == [("Acme", 3)] and b.llamadas == [("Acme", 7)]
    assert {m.headline for m in resultado.mentions} == {"Acme crece", "Acme invierte"}
    assert {m.source.source_type for m in resultado.mentions} == {SourceType.news_provider}
    assert {m.source.source_name for m in resultado.mentions} == {"Fuente fuente_a", "Fuente fuente_b"}


def test_estado_y_creditos_extra_por_fuente():
    ok = Falsa("con_notas", [_art("Acme", "https://x.example/1")])
    vacia = Falsa("vacia")
    caida = Falsa("caida", error=ProveedorNoticiasError("HTTP 500"))
    resultado = agent.collect_press_mentions(
        "Acme",
        fuentes=[
            agent.FuentePrensa(ok, limite=5, creditos_extra=2),
            agent.FuentePrensa(vacia, limite=5, creditos_extra=1),
            agent.FuentePrensa(caida, limite=5, creditos_extra=4),
        ],
    )
    estados = {f.clave: f.estado for f in resultado.fuentes}
    assert estados == {"con_notas": "consultada", "vacia": "sin_resultados", "caida": "error"}
    # Se cobra lo que respondió (con o sin resultados), nunca lo que falló.
    assert resultado.creditos_extra_usados == 3
    assert [f.provider for f in resultado.failed_providers] == ["caida"]


def test_sin_cupo_diario_no_consulta_ni_cobra(monkeypatch):
    llena = Falsa("llena", [_art("Acme", "https://x.example/1")])
    monkeypatch.setattr(agent, "reservar_consulta", lambda clave, limite, **_: False)
    resultado = agent.collect_press_mentions(
        "Acme",
        fuentes=[agent.FuentePrensa(llena, limite=5, creditos_extra=3, limite_diario=10, contar_uso=True)],
    )
    assert llena.llamadas == []
    assert [f.estado for f in resultado.fuentes] == ["limite_diario"]
    assert resultado.creditos_extra_usados == 0
    assert resultado.mentions == []


def test_cuenta_el_uso_solo_si_se_pide(monkeypatch):
    reservas: list[tuple[str, int | None]] = []
    monkeypatch.setattr(
        agent, "reservar_consulta", lambda clave, limite, **_: reservas.append((clave, limite)) or True
    )
    contada, libre = Falsa("contada"), Falsa("libre")
    agent.collect_press_mentions(
        "Acme",
        fuentes=[
            agent.FuentePrensa(contada, limite=5, limite_diario=None, contar_uso=True),
            agent.FuentePrensa(libre, limite=5),
        ],
    )
    assert reservas == [("contada", None)]


def test_sin_fuentes_no_consulta_nada():
    resultado = agent.collect_press_mentions("Acme", fuentes=[])
    assert resultado.mentions == [] and resultado.fuentes == [] and resultado.failed_providers == []


def test_por_defecto_solo_las_activas_con_clave(monkeypatch):
    monkeypatch.delenv("NEWS_API_KEY", raising=False)
    claves = [f.proveedor.clave for f in agent.fuentes_por_defecto()]
    assert claves == ["gdelt_news"]
    monkeypatch.setenv("NEWS_API_KEY", "clave")
    assert sorted(f.proveedor.clave for f in agent.fuentes_por_defecto()) == ["gdelt_news", "news_api"]


def test_el_resumen_inventado_no_cuenta_para_homonimos():
    """Sin resumen del proveedor se arma uno con el medio: el medio no prueba nada."""
    fuente = Falsa(
        "sin_resumen",
        [ArticuloNoticia(titulo="Resultados del trimestre", url="https://acme.example/n", medio="acme.example")],
    )
    resultado = agent.collect_press_mentions("Acme", fuentes=[agent.FuentePrensa(fuente, limite=5)])
    (mencion,) = resultado.mentions
    assert "acme.example" in mencion.summary
    conservadas, descartadas = agent.filtrar_homonimos([mencion], "Acme")
    assert conservadas == [] and descartadas == 1


# --- Motivo real del fallo (límite de consultas, tiempo de espera) -------------------------


def test_el_resultado_distingue_limite_de_consultas_y_error():
    from dossier.news.client import LimiteProveedorNoticias

    limitada = Falsa("limitada", error=LimiteProveedorNoticias("HTTP 429"))
    caida = Falsa("caida", error=ProveedorNoticiasError("HTTP 500"))
    resultado = agent.collect_press_mentions(
        "Acme", fuentes=[agent.FuentePrensa(limitada, limite=5), agent.FuentePrensa(caida, limite=5)]
    )
    motivos = {f.clave: f.motivo for f in resultado.fuentes}
    assert motivos == {"limitada": "provider_rate_limit", "caida": "provider_error"}
    assert agent.motivo_de_fallo(resultado) == "provider_error"
    solo_limite = agent.collect_press_mentions("Acme", fuentes=[agent.FuentePrensa(limitada, limite=5)])
    assert agent.motivo_de_fallo(solo_limite) == "provider_rate_limit"
