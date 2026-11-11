"""Fuentes de prensa que usa cada dossier según los ajustes del administrador (UX-ADMIN-02).

Ver ``specs/proposals/UX-ADMIN-02-fuentes-noticias.md``. Una fuente sin fila en
``news_source_settings`` usa los valores de su adaptador (las nuevas, apagadas).

- ``seleccionar_fuentes``: lógica pura; qué fuentes entran según tipo de dossier,
  profundidad (solo empresas), plan, interruptores y si tiene su clave configurada.
- ``fuentes_aplicables``: lo mismo leyendo los ajustes con la sesión de quien llama (nunca
  una conexión global). Si la lectura falla se usan los valores por defecto, sin contar uso:
  un dossier no se cae por los ajustes de la prensa.
- ``reservar_consulta``: anota una consulta del día (UTC) y respeta el límite diario sin
  carreras: ``INSERT … ON CONFLICT DO UPDATE … WHERE queries < límite``.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from dossier.billing.credit_policy import credit_charging_enabled
from dossier.billing.plan_catalog import normalize_plan
from dossier.db.models import NewsSourceSetting
from dossier.news.agent import FuentePrensa
from dossier.news.proveedores.base import ProveedorNoticias
from dossier.news.proveedores.registro import proveedores_instalados

logger = logging.getLogger(__name__)

TipoDossier = Literal["corporate", "person"]
PROFUNDIDADES: Final = ("basic", "standard", "deep")
PLANES: Final = ("free", "pro", "enterprise")
MAX_CREDITOS_EXTRA: Final = 20
MAX_RESULTADOS: Final = 50
MAX_LIMITE_DIARIO: Final = 100_000
RESULTADOS_POR_DEFECTO: Final = 10


@dataclass(frozen=True)
class AjusteFuente:
    clave: str
    enabled: bool
    use_for_corporate: bool = True
    use_for_person: bool = True
    # Solo dossiers de empresa: las personas siempre son de profundidad básica.
    min_depth: str = "basic"
    plans: frozenset[str] = field(default_factory=lambda: frozenset(PLANES))
    extra_credits: int = 0
    max_results: int = RESULTADOS_POR_DEFECTO
    # Consultas por día (UTC); ``None`` = sin límite.
    daily_limit: int | None = None
    updated_at: datetime | None = field(default=None, compare=False)
    updated_by_user_id: UUID | None = field(default=None, compare=False)


def ajuste_por_defecto(proveedor: ProveedorNoticias) -> AjusteFuente:
    return AjusteFuente(clave=proveedor.clave, enabled=bool(proveedor.activo_por_defecto))


def ajuste_de_fila(fila: NewsSourceSetting) -> AjusteFuente:
    planes = {p for p, activo in (("free", fila.plan_free), ("pro", fila.plan_pro), ("enterprise", fila.plan_enterprise)) if activo}
    return AjusteFuente(
        clave=fila.provider_key,
        enabled=fila.enabled,
        use_for_corporate=fila.use_for_corporate,
        use_for_person=fila.use_for_person,
        min_depth=fila.min_depth,
        plans=frozenset(planes),
        extra_credits=fila.extra_credits,
        max_results=fila.max_results,
        daily_limit=fila.daily_limit,
        updated_at=fila.updated_at,
        updated_by_user_id=fila.updated_by_user_id,
    )


def completar_ajustes(
    instaladas: Mapping[str, ProveedorNoticias], guardados: Mapping[str, AjusteFuente]
) -> dict[str, AjusteFuente]:
    """Un ajuste por fuente instalada (guardado o por defecto); se ignoran las desinstaladas."""
    return {clave: guardados.get(clave) or ajuste_por_defecto(p) for clave, p in instaladas.items()}


def seleccionar_fuentes(
    instaladas: Mapping[str, ProveedorNoticias],
    ajustes: Mapping[str, AjusteFuente],
    *,
    tipo: TipoDossier,
    profundidad: str | None,
    plan: str | None,
    cobrar: bool,
    contar_uso: bool,
) -> list[FuentePrensa]:
    plan_id = normalize_plan(plan)
    nivel = PROFUNDIDADES.index(profundidad) if profundidad in PROFUNDIDADES else 0
    elegidas: list[FuentePrensa] = []
    for clave, proveedor in instaladas.items():
        ajuste = ajustes.get(clave) or ajuste_por_defecto(proveedor)
        if not ajuste.enabled or plan_id not in ajuste.plans or not proveedor.configurado():
            continue
        if tipo == "person" and not ajuste.use_for_person:
            continue
        if tipo == "corporate":
            minimo = PROFUNDIDADES.index(ajuste.min_depth) if ajuste.min_depth in PROFUNDIDADES else 0
            if not ajuste.use_for_corporate or nivel < minimo:
                continue
        elegidas.append(
            FuentePrensa(
                proveedor,
                limite=ajuste.max_results,
                creditos_extra=ajuste.extra_credits if cobrar else 0,
                limite_diario=ajuste.daily_limit,
                contar_uso=contar_uso,
            )
        )
    return elegidas


def creditos_extra_maximos(fuentes: Sequence[FuentePrensa]) -> int:
    """Lo máximo que puede sumar la prensa (si responden todas): para validar el saldo."""
    return sum(f.creditos_extra for f in fuentes)


# --- Con base de datos --------------------------------------------------------------------


def leer_ajustes(db: Session) -> dict[str, AjusteFuente]:
    guardados = {f.provider_key: ajuste_de_fila(f) for f in db.scalars(select(NewsSourceSetting)).all()}
    return completar_ajustes(proveedores_instalados(), guardados)


def fuentes_aplicables(
    db: Session,
    *,
    tipo: TipoDossier,
    profundidad: str | None,
    plan: str | None,
    cobrar: bool | None = None,
) -> list[FuentePrensa]:
    """Fuentes para un dossier, con los ajustes leídos con la sesión de quien llama.

    La lectura va en un SAVEPOINT: si falla (p. ej. tabla aún no creada) no arrastra la
    transacción del pedido. El uso diario se anota con el mismo motor de la sesión.
    """
    cobro = credit_charging_enabled() if cobrar is None else cobrar
    instaladas = proveedores_instalados()
    motor = None
    try:
        with db.begin_nested():
            ajustes = leer_ajustes(db)
        motor = db.get_bind()
    except Exception:
        logger.warning("No se pudieron leer los ajustes de prensa; se usan los valores por defecto", exc_info=True)
        ajustes = completar_ajustes(instaladas, {})
    elegidas = seleccionar_fuentes(
        instaladas, ajustes, tipo=tipo, profundidad=profundidad, plan=plan, cobrar=cobro,
        contar_uso=motor is not None,
    )
    return [replace(f, motor=motor) for f in elegidas] if motor is not None else elegidas


_RESERVAR = text(
    """
    INSERT INTO news_source_usage (provider_key, day, queries)
    VALUES (:clave, (now() AT TIME ZONE 'UTC')::date, 1)
    ON CONFLICT (provider_key, day) DO UPDATE
        SET queries = news_source_usage.queries + 1
        WHERE CAST(:limite AS INTEGER) IS NULL OR news_source_usage.queries < CAST(:limite AS INTEGER)
    RETURNING queries
    """
)


def reservar_consulta(clave: str, limite_diario: int | None, motor: Any) -> bool:
    """Anota una consulta de hoy (UTC). ``False`` si la fuente ya llegó a su límite diario.

    Va en su propia transacción (``motor.begin()``): la consulta cuenta aunque el dossier
    falle después, porque la fuente ya la cobró o la descontó de su cuota.
    """
    if limite_diario is not None and limite_diario <= 0:
        return False
    with motor.begin() as conexion:
        fila = conexion.execute(_RESERVAR, {"clave": clave, "limite": limite_diario}).first()
    return fila is not None


def uso_de_hoy(db: Session) -> dict[str, int]:
    filas = db.execute(
        text("SELECT provider_key, queries FROM news_source_usage WHERE day = (now() AT TIME ZONE 'UTC')::date")
    ).all()
    return {clave: int(n) for clave, n in filas}
