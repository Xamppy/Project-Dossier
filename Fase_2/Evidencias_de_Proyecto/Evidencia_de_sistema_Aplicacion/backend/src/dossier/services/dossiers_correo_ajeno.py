"""Marca dossiers de calendario guardados con el correo de otro asistente (BUG-2026-10-19-07).

Antes de BUG-2026-10-19-02, en una reunión con varios asistentes, el dossier de quien no
declaraba correo se guardaba con el de otro asistente (``subject_email`` y
``person_filters.email``). El parse no se guarda, así que la detección se hace entre filas
hermanas: dossiers de persona del mismo ``dossier_folder_id`` (un evento, una ejecución) que
comparten correo con nombres distintos. Spec:
``specs/proposals/BUG-2026-10-19-07-dossiers-correo-ajeno.md``.

No borra nada: anula el correo, guarda el anterior en ``dossier_data.correo_sospechoso`` y
por defecto solo simula. Entrada de línea de comandos:
``backend/scripts/marcar_dossiers_correo_ajeno.py``.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session

TAREA = "BUG-2026-10-19-07"
CLAVE_MARCA = "correo_sospechoso"
MOTIVO_AJENO = "correo_de_otro_asistente"
MOTIVO_SIN_DUENO = "correo_compartido_sin_dueno"


@dataclass(frozen=True)
class FilaDossier:
    """Lo que la detección necesita de un dossier de persona guardado."""

    dossier_id: str
    grupo: str | None
    subject_name: str | None
    correo: str | None
    ya_marcado: bool = False


@dataclass(frozen=True)
class Afectado:
    dossier_id: str
    correo: str
    motivo: str
    presunto_dueno: dict[str, str] | None
    comparte_con: list[dict[str, str]] = field(default_factory=list)


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _normalizar_nombre(nombre: str | None) -> str:
    return re.sub(r"\s+", " ", _sin_acentos(nombre or "").strip()).casefold()


def _normalizar_correo(correo: str | None) -> str:
    return (correo or "").strip().casefold()


def nombre_aparece_en_correo(nombre: str | None, correo: str | None) -> bool:
    """Algún token del nombre es un token de la parte local o está contenido en ella.

    Igualdad desde 2 letras (``jose`` en ``jose_n``); contención desde 3 (``perez`` en
    ``jperez``), para que iniciales sueltas no coincidan con cualquier cosa.
    """
    correo_n = _normalizar_correo(correo)
    if "@" not in correo_n:
        return False
    local = _sin_acentos(correo_n.split("@", 1)[0])
    tokens_local = {t for t in re.split(r"[._+\-]+", local) if t}
    for token in re.split(r"[^a-z0-9]+", _normalizar_nombre(nombre)):
        if len(token) >= 2 and token in tokens_local:
            return True
        if len(token) >= 3 and token in local:
            return True
    return False


def fila_desde_dossier(
    *,
    dossier_id: Any,
    dossier_folder_id: Any,
    subject_name: str | None,
    subject_email: str | None,
    dossier_data: Any,
) -> FilaDossier:
    """Grupo = ``dossier_folder_id`` o ``calendar_folder.id``; correo = ``subject_email`` o
    ``person_filters.email``."""
    data = dossier_data if isinstance(dossier_data, dict) else {}
    carpeta = data.get("calendar_folder")
    grupo = dossier_folder_id or (carpeta.get("id") if isinstance(carpeta, dict) else None)
    filtros = data.get("person_filters")
    correo = subject_email or (filtros.get("email") if isinstance(filtros, dict) else None)
    return FilaDossier(
        dossier_id=str(dossier_id),
        grupo=str(grupo) if grupo else None,
        subject_name=subject_name,
        correo=correo or None,
        ya_marcado=CLAVE_MARCA in data,
    )


def _ref(fila: FilaDossier) -> dict[str, str]:
    return {"dossier_id": fila.dossier_id, "subject_name": fila.subject_name or ""}


def detectar_afectados(filas: Iterable[FilaDossier]) -> list[Afectado]:
    """Dossiers de persona que comparten correo con otro asistente del mismo grupo."""
    por_grupo: dict[str, list[FilaDossier]] = defaultdict(list)
    for fila in filas:
        if fila.grupo:
            por_grupo[fila.grupo].append(fila)

    afectados: list[Afectado] = []
    for grupo in sorted(por_grupo):
        miembros = por_grupo[grupo]
        if len(miembros) < 2:  # un solo asistente: el correo del evento es suyo
            continue
        por_correo: dict[str, list[FilaDossier]] = defaultdict(list)
        for fila in miembros:
            correo = _normalizar_correo(fila.correo)
            if correo and not fila.ya_marcado:
                por_correo[correo].append(fila)

        for correo in sorted(por_correo):
            comparten = sorted(por_correo[correo], key=lambda f: f.dossier_id)
            identidades = {_normalizar_nombre(f.subject_name) for f in comparten}
            if len(identidades) < 2:
                continue
            duenas = {i for i in identidades if nombre_aparece_en_correo(i, correo)}
            dueno = next(iter(duenas)) if len(duenas) == 1 else None
            presunto = None
            if dueno is not None:
                presunto = _ref(next(f for f in comparten if _normalizar_nombre(f.subject_name) == dueno))
            for fila in comparten:
                if dueno is not None and _normalizar_nombre(fila.subject_name) == dueno:
                    continue
                afectados.append(
                    Afectado(
                        dossier_id=fila.dossier_id,
                        correo=correo,
                        motivo=MOTIVO_AJENO if dueno is not None else MOTIVO_SIN_DUENO,
                        presunto_dueno=presunto,
                        comparte_con=[_ref(o) for o in comparten if o is not fila],
                    )
                )
    return afectados


def marcar_dossier_data(
    dossier_data: Any,
    afectado: Afectado,
    *,
    correo_anterior: str | None,
    ahora: datetime,
) -> dict[str, Any]:
    """Copia de ``dossier_data`` con la marca y ``person_filters.email`` anulado si era el ajeno."""
    nuevo = json.loads(json.dumps(dossier_data)) if isinstance(dossier_data, dict) else {}
    filtros = nuevo.get("person_filters")
    filtros_email = filtros.get("email") if isinstance(filtros, dict) else None
    if isinstance(filtros, dict) and _normalizar_correo(filtros_email) == afectado.correo:
        filtros["email"] = None
    nuevo[CLAVE_MARCA] = {
        "tarea": TAREA,
        "motivo": afectado.motivo,
        "correo_anterior": correo_anterior,
        "person_filters_email_anterior": filtros_email,
        "presunto_dueno": afectado.presunto_dueno,
        "comparte_con": afectado.comparte_con,
        "marcado_en": ahora.isoformat(),
    }
    return nuevo


def marcar_dossiers_correo_ajeno(
    db: Session,
    *,
    aplicar: bool,
    ahora: datetime | None = None,
) -> dict[str, Any]:
    """Detecta y, solo si ``aplicar``, marca los afectados en una transacción. Devuelve el informe."""
    from sqlalchemy import select

    from dossier.db.models import Dossier

    consulta = select(Dossier).where(
        Dossier.dossier_data["calendar_folder_role"].astext == "person"
    )
    if aplicar:
        consulta = consulta.with_for_update()
    dossiers = {str(d.id): d for d in db.execute(consulta).scalars()}
    filas = [
        fila_desde_dossier(
            dossier_id=d.id,
            dossier_folder_id=d.dossier_folder_id,
            subject_name=d.subject_name,
            subject_email=d.subject_email,
            dossier_data=d.dossier_data,
        )
        for d in dossiers.values()
    ]
    afectados = detectar_afectados(filas)
    momento = ahora or datetime.now(UTC)

    informe_afectados = []
    for afectado in afectados:
        d = dossiers[afectado.dossier_id]
        correo_anterior = d.subject_email
        informe_afectados.append(
            {
                "dossier_id": afectado.dossier_id,
                "organization_id": str(d.organization_id),
                "subject_name": d.subject_name,
                "correo_anterior": correo_anterior or afectado.correo,
                "motivo": afectado.motivo,
                "presunto_dueno": afectado.presunto_dueno,
            }
        )
        if aplicar:
            d.dossier_data = marcar_dossier_data(
                d.dossier_data, afectado, correo_anterior=correo_anterior, ahora=momento
            )
            d.subject_email = None

    if aplicar:
        db.commit()
    else:
        db.rollback()

    return {
        "tarea": TAREA,
        "modo": "aplicado" if aplicar else "simulacion",
        "revisados": len(filas),
        "grupos_revisados": len({f.grupo for f in filas if f.grupo}),
        "ya_marcados": sum(1 for f in filas if f.ya_marcado),
        "afectados": informe_afectados,
    }


def main(argv: list[str] | None = None, *, engine: Engine | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Marca dossiers de calendario guardados con el correo de otro asistente "
            f"({TAREA}). Por defecto solo simula."
        )
    )
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--dry-run", action="store_true", help="Simula sin escribir (por defecto).")
    modo.add_argument("--aplicar", action="store_true", help="Escribe los cambios.")
    args = parser.parse_args(argv)

    from sqlalchemy.orm import Session

    if engine is None:
        from dossier.db.connection import get_engine

        engine = get_engine()
    with Session(engine) as db:
        informe = marcar_dossiers_correo_ajeno(db, aplicar=args.aplicar)
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    return 0
