# PostgreSQL en Sistema Dossier

Las credenciales **no van en el código** ni en el repositorio. Cada persona copia `.env.example` a `.env` y pone su propia base local (o remota).

## Variables

### Opción A — URL única

```
DATABASE_URL=postgresql+psycopg://usuario:contraseña@localhost:5432/nombre_bd
```

Si la contraseña tiene caracteres especiales, codifícala en la URL o usa la opción B.

### Opción B — Variables separadas

```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=tu_clave_local
POSTGRES_DB=dossier
```

Opcional: `POSTGRES_POOL_SIZE`, `POSTGRES_MAX_OVERFLOW`.

## Código

| Módulo | Uso |
|--------|-----|
| `dossier.db.settings.build_database_url()` | Construye la URL desde el entorno |
| `dossier.db.is_database_configured()` | `True` si hay `DATABASE_URL` o `POSTGRES_HOST` + `POSTGRES_DB` |
| `dossier.db.get_engine()` | Motor SQLAlchemy (singleton) |
| `dossier.db.get_db` | Dependencia FastAPI `Depends(get_db)` |
| `dossier.db.dispose_engine()` | Cerrar pool (tests / shutdown) |

## Schema SQL (migración v1.0)

Ejecuta en PostgreSQL el script consolidado:

- **[sql/schema_project_dossier.sql](sql/schema_project_dossier.sql)** (mismo contenido que `backend/src/dossier/db/Migracion.md`).

Incluye extensiones `uuid-ossp` y `pgcrypto`, tablas multi-tenant (`organizations`, `users`, `org_memberships`, `dossiers`, …) y triggers.

Si tu base se creó con una **versión antigua** del DDL y falla el `INSERT` en `dossiers` con error de FK en `credit_ledger`, aplica el parche idempotente:

- **[../backend/scripts/fix_dossier_credit_triggers.sql](../backend/scripts/fix_dossier_credit_triggers.sql)** (SQL puro; en Windows hace falta `psql` en el PATH), o bien
- **`python scripts/apply_fix_dossier_credit_triggers.py`** desde `backend/` (usa tu `.env` y `psycopg`, sin `psql`).

Tras aplicarlo, puedes desactivar la creación automática de tablas al arrancar la API con **`DATABASE_AUTO_CREATE_TABLES=0`** en `.env` (ver [auth-app.md](auth-app.md)).

## Mantenimiento de datos

Correcciones de datos ya guardados. No cambian el esquema, por eso no están en
`db/Migracion.md` ni en Alembic: se ejecutan a mano, una vez por ambiente, después de revisar la
simulación.

### Dossiers con el correo de otro asistente (BUG-2026-10-19-07)

Antes de BUG-2026-10-19-02, en reuniones con varios asistentes, el dossier de quien no tenía
correo propio se guardaba con el de otro asistente. El script detecta esos dossiers (los de
persona de un mismo evento y ejecución que comparten correo con nombres distintos), les anula
`subject_email` y `person_filters.email`, y guarda el valor anterior en
`dossier_data.correo_sospechoso`. No borra nada y es idempotente. Detalle y límites:
[specs/proposals/BUG-2026-10-19-07-dossiers-correo-ajeno.md](../specs/proposals/BUG-2026-10-19-07-dossiers-correo-ajeno.md).

Desde `backend/`, con la `DATABASE_URL` del ambiente en `.env`:

```bash
python scripts/marcar_dossiers_correo_ajeno.py            # simulación: imprime el informe JSON
python scripts/marcar_dossiers_correo_ajeno.py --dry-run  # lo mismo, explícito
python scripts/marcar_dossiers_correo_ajeno.py > informe-bug07.json   # guarda el informe para revisarlo
python scripts/marcar_dossiers_correo_ajeno.py --aplicar  # escribe, en una sola transacción
```

Revisa `afectados` en la simulación antes de aplicar. Una segunda ejecución con `--aplicar`
debe devolver `afectados: []`. Para deshacer un caso, los valores anteriores están en
`dossier_data->'correo_sospechoso'`: `correo_anterior` (era `subject_email`) y
`person_filters_email_anterior` (era `person_filters.email`). Uno de los dos puede ser null si
el correo ajeno solo estaba en el otro campo.

## Comprobar conexión

Con el backend en marcha:

```http
GET /db/health
```

- Sin `.env` de base: `postgresql: not_configured`
- Con datos correctos: `postgresql: ok`
- Error de red o credenciales: `503` con `detail`

## Compartir el proyecto

1. Subes **solo** `.env.example` (sin secretos).
2. Cada colaborador crea su `.env` (git lo ignora).
3. Nadie depende de la contraseña de otro.

## Ejecutar módulos desde el IDE

Si usas **Run Python File** sobre `settings.py`, `connection.py` o `session.py`, el código añade automáticamente la carpeta `src/` al path cuando `dossier` no está instalado.

La forma recomendada sigue siendo:

```powershell
cd SistemaDossier/backend
uvicorn main:app --reload
```

o, para una prueba rápida:

```powershell
$env:PYTHONPATH="src"
python -c "from dossier.db.settings import build_database_url; print(build_database_url())"
```
