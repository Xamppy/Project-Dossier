# UX-ADMIN-01 · Panel de administración: dossiers simultáneos por usuario según el plan

- **Tarea:** UX-ADMIN-01, ampliación solicitada por FD el 2026-11-11 (fuera de las tareas del plan).
- **Responsable:** FD
- **Objetivo:** OE6 (dashboard) · **Estado:** implementada · verificación en
  `specs/reports/UX-ADMIN-01-limites-por-plan.md`

## Problema

Un usuario puede encolar todos los dossiers que quiera a la vez. Cada uno consume trabajo del
servidor y llamadas a proveedores pagados (DeepSeek, PDL, registros). No hay forma de acotarlo
según el plan, ni un lugar donde el equipo que opera la plataforma ajuste estos valores.

## Decisión (aprobada por FD el 2026-11-11)

- Lo configura **solo el admin de plataforma** (`users.is_platform_admin`), en el panel existente
  `/dashboard/admin`, sección nueva **«Límites por plan»**. Los clientes no lo tocan.
- Valores iniciales: **Free 1 · Pro 3 · Enterprise 10** dossiers generándose a la vez por usuario.
- Los dossiers que genera sola la **automatización del calendario no cuentan** ni se bloquean: una
  reunión no debe quedarse sin dossier por el tope.
- El panel queda preparado para sumar más ajustes por plan.

## Diseño

### Datos

Tabla `plan_settings` (migración Alembic + `schema_patches`):

| Columna | Tipo |
|---|---|
| `plan` | `VARCHAR(20)` PK, `CHECK (plan IN ('free','pro','enterprise'))` |
| `max_concurrent_dossiers` | `INTEGER NOT NULL`, `CHECK (1 ≤ valor ≤ 100)` |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `updated_by_user_id` | `UUID` → `users(id) ON DELETE SET NULL` |

La migración inserta los valores iniciales (`ON CONFLICT DO NOTHING`). Si falta la fila de un plan,
se usa el valor inicial.

### Control (servidor)

- Al encolar un dossier de **Personas** o de **Calendario** pedido por el usuario
  (`person_manual`, `calendar_manual`), se bloquea su fila de `users` (`FOR UPDATE`) y se cuentan
  sus trabajos `queued`/`running` en esa organización.
- Solo cuentan los creados en los últimos `DOSSIER_CONCURRENCY_WINDOW_MINUTES` (30): un trabajo que
  quedó «en curso» por una caída del servidor no bloquea al usuario para siempre.
- Un pedido igual a uno ya activo (deduplicación existente) no cuenta como nuevo.
- Calendario con varias reuniones en una petición: se comprueba **antes de encolar ninguna**
  (todo o nada); cada encolado vuelve a comprobar con la fila bloqueada.
- Si se supera: **409** con `detail = {"code": "CONCURRENT_DOSSIER_LIMIT", "limit": N, "active": M}`.
  No es 429: el frontend traduce todo 429 como «espera N segundos», que aquí no aplica.

### Administración

- `GET /admin/plan-settings` → los tres planes con su límite, fecha y autor del último cambio.
- `PATCH /admin/plan-settings/{plan}` con `{"max_concurrent_dossiers": n}` (1–100).
- Ambas exigen admin de plataforma (401 sin sesión, 403 sin el permiso).
- Cada cambio queda en `audit_logs` (`ADMIN plan_settings`, valor anterior y nuevo).

### Frontend

- Sección «Límites por plan» en `/dashboard/admin`: una fila por plan con un campo numérico y
  «Guardar». Error y confirmación visibles.
- El error 409 se muestra traducido: «Ya tienes {limit} dossiers generándose…».
- Textos en los seis catálogos propios (en-gb hereda de en).

## Criterios de aceptación

| CA | Criterio |
|---|---|
| CA1 | La migración crea `plan_settings` con Free 1, Pro 3, Enterprise 10 y el downgrade la quita |
| CA2 | Con el tope alcanzado, pedir otro dossier de Personas o de Calendario devuelve 409 `CONCURRENT_DOSSIER_LIMIT` y no crea el trabajo |
| CA3 | Al terminar, fallar o cancelarse un trabajo, el usuario puede pedir otro |
| CA4 | El tope es por usuario: otro usuario de la misma organización no se ve afectado |
| CA5 | Los trabajos activos de más de 30 minutos y los automáticos no cuentan |
| CA6 | Un pedido duplicado de uno activo devuelve el existente aunque el tope esté lleno |
| CA7 | Calendario con varias reuniones que superan el tope: 409 y ninguna encolada |
| CA8 | Peticiones simultáneas no superan el tope (bloqueo de la fila del usuario) |
| CA9 | Solo el admin de plataforma lee y cambia los límites; valores fuera de 1–100 o plan desconocido → 422/404; cada cambio queda auditado |
| CA10 | El panel muestra y guarda los límites; el error 409 se ve traducido en los siete idiomas |
