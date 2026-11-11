"""UX-ADMIN-01 · Estrés del tope de dossiers a la vez (Postgres).

Cinco usuarios Pro (tope 3) piden seis dossiers cada uno, los 30 a la vez. Con el bloqueo de
la fila del usuario, cada uno termina con exactamente 3 trabajos y el resto recibe 409.
Requiere ``TEST_DATABASE_URL``.
"""
from __future__ import annotations

import threading
from collections import Counter

from sqlalchemy import text

from tests.integration.test_limite_dossiers_simultaneos import (  # noqa: F401
    base,
    cliente,
    org,
    pedir_persona,
    usuario,
)

USUARIOS = 5
PEDIDOS = 6


def test_treinta_pedidos_simultaneos_de_cinco_usuarios(base):  # noqa: F811
    with base.engine.begin() as c:
        ids = [usuario(c, f"u{i}@carga.com", base.pro) for i in range(USUARIOS)]

    resultados: Counter[tuple[int, int]] = Counter()
    candado = threading.Lock()
    barrera = threading.Barrier(USUARIOS * PEDIDOS)

    def pedir(n_usuario: int, n_pedido: int) -> None:
        c = cliente(ids[n_usuario], base.pro)
        barrera.wait()
        estado = pedir_persona(c, f"Carga {n_usuario}-{n_pedido}").status_code
        with candado:
            resultados[(n_usuario, estado)] += 1

    hilos = [threading.Thread(target=pedir, args=(u, p)) for u in range(USUARIOS) for p in range(PEDIDOS)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    for u in range(USUARIOS):
        assert resultados[(u, 200)] == 3, resultados
        assert resultados[(u, 409)] == 3, resultados
    with base.engine.connect() as c:
        por_usuario = dict(
            c.execute(
                text(
                    "SELECT requested_by_user_id, count(*) FROM dossier_generation_jobs "
                    "WHERE organization_id = :o GROUP BY 1"
                ),
                {"o": base.pro},
            ).all()
        )
    assert sorted(por_usuario.values()) == [3] * USUARIOS
