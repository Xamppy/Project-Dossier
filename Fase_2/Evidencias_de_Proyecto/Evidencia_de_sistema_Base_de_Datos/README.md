# Evidencia de sistema: Base de Datos

Base de datos de Project Dossier: PostgreSQL 16 (en el despliegue) con el esquema versionado mediante
Alembic. Esta carpeta reúne la evidencia de cómo se crea y se usa; el código vive en la carpeta del
sistema, `../Evidencia_de_sistema_Aplicacion/`.

| Carpeta | Qué demuestra |
|---|---|
| [migraciones/](migraciones/README.md) | `alembic upgrade head` sobre una base vacía aplica las 3 revisiones y deja 22 tablas, 2 vistas, 9 triggers y 3 funciones propias. Incluye el diagrama entidad-relación del ORM ([modelo-datos.md](migraciones/modelo-datos.md)). |
| [almacenamiento/](almacenamiento/README.md) | Las 109 pruebas que necesitan PostgreSQL pasan contra una base real, y los datos ficticios generados por la API quedan en organizaciones, usuarios (bcrypt), jobs, dossiers (`dossier_data` JSONB) y el ledger de créditos. |

## Dónde está el esquema en el código

Rutas relativas a `../Evidencia_de_sistema_Aplicacion/`:

- `backend/alembic/versions/`: las migraciones versionadas (`a3f1c9e2b7d4` → `b7e2d4f1a9c3` → `c4d8a2f6b1e9`).
- `backend/src/dossier/db/models.py`: el modelo ORM (SQLAlchemy).
- `backend/src/dossier/db/Migracion.md` y `docs/sql/`: el DDL documentado.
- `docs/postgresql.md`: conexión, variables de entorno y operación.

Las evidencias se obtuvieron con bases desechables y datos ficticios; no contienen datos personales.
