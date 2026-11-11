# Documentación técnica · Project Dossier (TraceLens)

Versión del 2026-11-11, rama `docmac`. Tarea S7.6.

Este documento es el **punto de entrada** para instalar, desplegar y operar el sistema. Cuando un
tema ya tiene una guía detallada, aquí va el resumen y el enlace. El manual para quien usa el
dashboard está en [`../manual-usuario/README.md`](../manual-usuario/README.md).

> Se adelantó al congelamiento de funcionalidades (S7.0, pendiente). Revisar después de S7.0.

## Contenido

1. [Arquitectura](#1-arquitectura)
2. [Requisitos](#2-requisitos)
3. [Instalación local](#3-instalación-local)
4. [Despliegue](#4-despliegue)
5. [Variables de entorno](#5-variables-de-entorno)
6. [Operación](#6-operación)
7. [Pruebas y calidad](#7-pruebas-y-calidad)
8. [Registro de decisiones técnicas](#8-registro-de-decisiones-técnicas)
9. [Problemas conocidos](#9-problemas-conocidos)

---

## 1. Arquitectura

```
navegador ──HTTPS──► Caddy (o Dokploy/Traefik)
                       ├── /api/* ──► backend: FastAPI (un proceso) ──► PostgreSQL 16+
                       │                 ├─ hilo: worker de generación   └──► Redis (caché, opcional)
                       │                 ├─ hilo: automatización de calendario
                       │                 ├─ hilo: retención de 24 h
                       │                 ├─ hilo: reintentos de correo
                       │                 └─ bus en memoria de los canales SSE
                       └── resto ────► frontend: Next.js 16 (React 19)
proveedores externos: DeepSeek (IA), People Data Labs, Companies House, SEC EDGAR,
recherche-entreprises (FR), OffeneRegister (DE), GDELT, NewsAPI, Google y Microsoft (OAuth), SMTP
```

| Pieza | Dónde | Qué hace |
|---|---|---|
| API | `backend/src/dossier/api/` | Autenticación (JWT de 15 min y refresh token en cookie), dossiers, trabajos, canales SSE, administración |
| Grafo corporativo | `backend/src/dossier/graphs/corporate_dossier_graph.py` | LangGraph: agentes de Reino Unido, EE. UU., Europa y prensa en paralelo, y luego la síntesis con IA |
| Investigación de personas | `backend/src/dossier/services/person_research_*.py` | PDL (o web pública) más síntesis estructurada con IA |
| Trabajos | `services/dossier_generation_job_service.py` y `services/dossier_generation_worker.py` | Cola en `dossier_generation_jobs`, procesada por un hilo con latido; recuperación de colgados |
| Esquema | `backend/alembic/` y `src/dossier/db/schema_patches.py` | Migraciones Alembic (la cabeza es `d4f6a8c2e0b3`) y los mismos parches idempotentes al arrancar |
| Frontend | `frontend/src/` | Dashboard Next.js; siete idiomas en `src/i18n/messages/` |

**Un solo proceso a propósito.** Los workers son hilos de la API y el bus de los canales en vivo
vive en su memoria. Por eso `docker-entrypoint.sh` arranca uvicorn con `--workers 1`. Con varias
réplicas, el canal de un trabajo solo se actualiza al instante en la réplica que lo procesa; las
demás lo ven en su siguiente lectura de la base (cada 10 s). Los límites de tasa también están en
memoria.

Más detalle: [`../estructura.md`](../estructura.md),
[`../langgraph-dossier.md`](../langgraph-dossier.md) y
[`../architecture/inventario-modulos.md`](../architecture/inventario-modulos.md).

## 2. Requisitos

| Herramienta | Versión | Nota |
|---|---|---|
| Python | 3.12 | El backend usa `target-version = "py312"` |
| Node.js | 20+ | Next.js 16 |
| PostgreSQL | 16+ (probado con 16 y 18) | Extensiones `uuid-ossp` y `pgcrypto`; triggers PL/pgSQL |
| Redis | 7 (opcional) | Caché de informes y bloqueos; sin Redis la caché se apaga |
| Docker + Compose v2 | Para el despliegue | — |

Claves de terceros: solo `DEEPSEEK_API_KEY` es imprescindible para generar dossiers. Cada
integración sin clave se apaga sola, y `GET /` informa cuáles quedaron activas (`config_check`).

## 3. Instalación local

Guía completa: [`../dev/local-setup.md`](../dev/local-setup.md). Resumen en Windows (PowerShell):

```powershell
# 1. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env      # completa DATABASE_URL, JWT_SECRET (16+ caracteres) y DEEPSEEK_API_KEY

# 2. Base de datos: crea la base vacía y aplica el esquema completo
$env:DATABASE_URL="postgresql://usuario:clave@localhost:5432/dossier"
alembic upgrade head        # 27 tablas (más alembic_version), 2 vistas y los triggers de cobro

# 3. API en http://127.0.0.1:8000 (documentación interactiva en /docs)
python -m uvicorn dossier.api.app:app --app-dir src --host 127.0.0.1 --port 8000

# 4. Frontend en http://localhost:3000 (otra terminal)
cd ..\frontend
npm ci
copy .env.local.example .env.local    # NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
npm run dev
```

Comprobación: `GET http://127.0.0.1:8000/health` responde 200 y `GET /db/health` confirma la
base. Crea la primera cuenta en `http://localhost:3000/register`.

**Correo sin un servidor real:** cualquier servidor SMTP de prueba en `localhost:1025` sirve, con
`SMTP_HOST=127.0.0.1`, `SMTP_PORT=1025` y `SMTP_SECURITY=none`. Ver
[`../dev/correo-gmail.md`](../dev/correo-gmail.md#3-probar-sin-gmail).

## 4. Despliegue

Guía completa, con Docker Compose más Caddy, o con Dokploy desde GitHub:
[`../dev/despliegue-vps.md`](../dev/despliegue-vps.md).

```bash
cd deploy
cp .env.example .env     # DOMAIN, ACME_EMAIL, POSTGRES_PASSWORD, JWT_SECRET y las claves de terceros
docker compose up -d --build
```

- Al arrancar, la API ejecuta `alembic upgrade head` (`RUN_MIGRATIONS=0` lo evita) y aplica los
  parches de esquema.
- Un solo dominio sirve el dashboard en `/` y la API en `/api` (`API_ROOT_PATH`), sin CORS.
- OAuth: hay que registrar las URI de retorno del dominio en Google Cloud y en Azure. Ver
  [`../calendario-oauth-operaciones.md`](../calendario-oauth-operaciones.md) y
  [`../dev/despliegue-vps.md`](../dev/despliegue-vps.md#oauth-de-calendarios).

**Actualizar:** `git pull` y `docker compose up -d --build`. Las migraciones nuevas se aplican
solas, y los trabajos que el reinicio deja a medias pasan a «fallido» en unos 3 minutos
(ver [6.3](#63-trabajos-colgados)).

## 5. Variables de entorno

Todas van en `backend/.env` (local) o `deploy/.env` (VPS). Las plantillas comentadas son
[`backend/.env.example`](../../backend/.env.example) y `deploy/.env.example`. La lista se obtuvo del
código (`os.getenv`) el 2026-11-11. «—» significa sin valor por omisión.

### 5.1 Imprescindibles

| Variable | Por omisión | Para qué |
|---|---|---|
| `DATABASE_URL` o `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | — | Conexión a PostgreSQL. `POSTGRES_POOL_SIZE` (5) y `POSTGRES_MAX_OVERFLOW` (10) ajustan el pool |
| `JWT_SECRET` | — | Firma de los tokens; 16 caracteres como mínimo. La API no arranca sin ella |
| `DEEPSEEK_API_KEY` | — | IA para los informes. Sin saldo en la cuenta, la generación falla (402) |
| `FRONTEND_URL` | — | URL pública del dashboard: retornos de OAuth y enlaces de los correos (`DOSSIER_FRONTEND_URL` tiene prioridad para los correos) |
| `CORS_ORIGINS` | — | Orígenes permitidos, separados por comas. No hace falta con un solo dominio |

### 5.2 Proveedores de datos

| Variable | Por omisión | Para qué |
|---|---|---|
| `PDL_API_KEY` (alias `PEOPLE_DATA_LABS_API_KEY`) | — | People Data Labs: perfiles de personas |
| `PDL_API_URL`, `PDL_MIN_LIKELIHOOD` | API pública, 2 | URL y confianza mínima de las coincidencias de PDL |
| `PERSON_RESEARCH_PROVIDER` | `pdl` | Fuente por omisión para los asistentes de una reunión |
| `COMPANIES_HOUSE_API_KEY` | — | Registro del Reino Unido |
| `SEC_USER_AGENT` | — | SEC EDGAR exige un User-Agent con contacto |
| `NEWS_API_KEY` | — | NewsAPI (GDELT no necesita clave). Sin ella NewsAPI no se consulta. Cada fuente de noticias agregada usa su propia variable ([guía](agregar-fuente-noticias.md)) |
| `EU_REGISTRY_DE_API_BASE`, `EU_REGISTRY_DE_DATABASE`, `EU_REGISTRY_DE_TABLE` | `https://db.offeneregister.de`, `openregister`, `company` | Registro alemán (OffeneRegister). El francés no necesita configuración |
| `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_TEXT_TIMEOUT_SEC` | `deepseek-chat`, API oficial, 120 | Modelo, endpoint y espera máxima por llamada |
| `DEEPSEEK_DISABLE_PERSON_WEB`, `DEEPSEEK_PERSON_WEB_ALWAYS`, `DEEPSEEK_PERSON_WEB_MODEL`, `DEEPSEEK_PERSON_MAX_JSON_CHARS` | — | Ajustes del análisis web de personas |
| `GEMINI_*`, `GOOGLE_API_KEY`, `DOSSIER_CORPORATE_CH_FILING_GEMINI`, `DOSSIER_CORPORATE_SEC_FILING_GEMINI`, `DOSSIER_SEC_*` | — | Línea heredada de Gemini y lectura de documentos regulatorios. Hoy la IA es DeepSeek (ADR 0001 y 0002); los nombres «gemini» se conservan por compatibilidad |

### 5.3 Inicio de sesión y calendarios (OAuth)

| Variable | Para qué |
|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Cliente OAuth de Google (calendario e inicio de sesión) |
| `GOOGLE_REDIRECT_URI` (alias `GOOGLE_REDIRECT_URL`) | Retorno del calendario: `<api>/callback-google` |
| `GOOGLE_LOGIN_REDIRECT_URI` | Retorno del inicio de sesión: `<api>/auth/google/callback` |
| `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID` (`common`) | Cliente de Azure para Outlook |
| `MICROSOFT_REDIRECT_URI` (alias `MICROSOFT_REDIRECT_URL`), `MICROSOFT_OAUTH_SUCCESS_URL` | Retorno de Outlook y página a la que vuelve el usuario |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (15), `REFRESH_TOKEN_EXPIRE_DAYS` (30, de 1 a 90) | Duración del token de acceso y de una sesión recordada |
| `AUTH_REFRESH_COOKIE_SECURE`, `AUTH_REFRESH_COOKIE_SAMESITE` | Cookie del refresh token (en producción: segura) |

### 5.4 Correo

| Variable | Para qué |
|---|---|
| `SMTP_HOST`, `SMTP_PORT` (587, o 465 con `ssl`), `SMTP_SECURITY` (`starttls` por omisión, `ssl` o `none`), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_TIMEOUT_SECONDS` | Servidor SMTP. Sin `SMTP_HOST`, el correo se apaga y el botón «Enviar por correo» responde 503 |
| `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME` | Remitente |
| `DOSSIER_ACCESS_LINK_HOURS` (24) | Vigencia del enlace de un solo uso del correo |

### 5.5 Workers, retención y límites

| Variable | Por omisión | Para qué |
|---|---|---|
| `DOSSIER_GENERATION_WORKER_ENABLED`, `DOSSIER_GENERATION_POLL_SECONDS` | 1, 2 | Worker de la cola de generación |
| `DOSSIER_JOB_HEARTBEAT_SECONDS`, `DOSSIER_JOB_STALE_SECONDS`, `DOSSIER_JOB_RECOVERY_SECONDS` | 30, 180, 60 | Latido de los trabajos y recuperación de colgados |
| `DOSSIER_RETENTION_WORKER_ENABLED`, `DOSSIER_RETENTION_HOURS`, `DOSSIER_RETENTION_POLL_SECONDS` | 1, 24, 600 | Borrado verificado de dossiers a las 24 h |
| `DOSSIER_EMAIL_RETRY_WORKER_ENABLED`, `DOSSIER_EMAIL_RETRY_POLL_SECONDS` | 1, 60 | Reintentos de correo (3 seguidos y luego cada 10 min, hasta 1 h) |
| `CALENDAR_AUTOMATION_ENABLED`, `CALENDAR_AUTOMATION_POLL_SECONDS`, `CALENDAR_DEFAULT_ADVANCE_MINUTES` | 1, 60, 20 | Generación automática antes de las reuniones |
| `DOSSIER_NOTIFICATIONS_CHECK_SECONDS`, `DOSSIER_NOTIFICATIONS_MAX_SECONDS` | 5, 600 | Canal en vivo de la campana |
| `DOSSIER_CONCURRENCY_WINDOW_MINUTES` | 30 | Antigüedad máxima de un trabajo activo para el tope de dossiers a la vez |
| `GENERATION_RATE_LIMIT`, `AUTH_RATE_LIMIT`, `LOGIN_FAILURE_RATE_LIMIT`, `ACCESS_LINK_RATE_LIMIT` | `10/60`, `20/60`, `5/300`, `20/60` | Límites de tasa con el formato `pedidos/segundos` (generación por usuario; autenticación, fallos de inicio de sesión y canjes de enlaces por IP o correo) |
| `DOSSIER_CHARGE_CREDITS` | `true` | `false` desactiva el cobro (solo para demos) |
| `ORG_SIGNUP_CREDITS`, `ORG_SIGNUP_CREDITS_MONTHLY_LIMIT` | 10, igual al anterior | Saldo y tope mensual de una organización nueva |
| `DOSSIER_REDIS_ENABLED`, `REDIS_URL`, `DOSSIER_REDIS_TTL_SECONDS` | 1, —, 86400 (con tope en la retención) | Caché de informes |
| `DOSSIER_CACHE_PIPELINE_VERSION`, `DOSSIER_PERSON_CACHE_VERSION` | — | Cambiarlas invalida la caché |
| `DATABASE_AUTO_CREATE_TABLES` | 1 | Crear las tablas al arrancar. En producción, 0: lo hace Alembic |
| `AUDIT_LOG_HMAC_KEY` | `JWT_SECRET` | Firma de la cadena de auditoría (`audit_logs`) |
| `RUN_MIGRATIONS`, `API_ROOT_PATH` | 1, `/api` | Solo en el contenedor (`docker-entrypoint.sh`) |

### 5.6 Frontend

| Variable | Para qué |
|---|---|
| `NEXT_PUBLIC_API_URL` | URL de la API vista desde el navegador. En el VPS se fija al compilar (`https://DOMAIN/api`) |

## 6. Operación

### 6.1 Salud y logs

- `GET /health` (200 si el proceso responde) y `GET /db/health` (conexión con la base). El
  contenedor usa el primero como healthcheck.
- `docker compose logs -f --tail=200 backend`. Los fallos de agentes, proveedores y correo
  quedan con su detalle técnico **solo en el log**, nunca en lo que ve el usuario (S7.2).

### 6.2 Respaldo y restauración

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > respaldo-$(date +%F).dump
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < respaldo.dump
```

Guardar los respaldos fuera del VPS. Ojo con la retención: los dossiers viven 24 h, así que un
respaldo restaurado días después trae dossiers que el worker borrará en su siguiente vuelta.

### 6.3 Trabajos colgados

Si la API se cae a mitad de una generación, el barrido de recuperación marca el trabajo como
`failed`, con un mensaje claro, en unos 3 minutos tras volver. No hay créditos que devolver: se
cobran al guardar el dossier. Consulta manual:

```sql
SELECT id, status, started_at, heartbeat_at FROM dossier_generation_jobs
WHERE status IN ('queued', 'running') ORDER BY created_at;
```

### 6.4 Administración de la plataforma

- **Dar el permiso de administrador de plataforma** (no hay botón, a propósito):
  `UPDATE users SET is_platform_admin = true WHERE email = 'persona@empresa.com';`
- En `/dashboard/admin` (sección «Límites por plan") se ajusta el tope de dossiers a la vez por
  plan (Free 1, Pro 3, Enterprise 10 al inicio). Cada cambio queda en `audit_logs`.
- En la sección «Fuentes de noticias» se decide cuándo se usa cada fuente de prensa: empresas o
  personas, profundidad mínima, planes, créditos extra, máximo de noticias y límite diario. Las
  claves siguen en el entorno del servidor. Para conectar otra API:
  [Agregar una fuente de noticias](agregar-fuente-noticias.md).
- **Cambiar el plan de una organización:** `PATCH /organization/plan`, que puede usar el
  administrador de esa organización. Ajusta los créditos según `billing/plan_catalog.py`. No hay
  pasarela de pago: ver [9](#9-problemas-conocidos).

### 6.5 Auditoría y retención

- `audit_logs` es de solo inserción, con una cadena HMAC. Registra rutas sensibles, trabajos,
  envíos de correo, borrados por retención, canjes de enlaces y cambios de administración.
- La retención borra dossiers, trabajos terminados, enlaces y caché, y deja un registro
  `RETENTION verification`. Ver `services/dossier_retention_worker.py`.

### 6.6 Rotar secretos

- `JWT_SECRET`: invalida todas las sesiones; los usuarios vuelven a entrar. Si `AUDIT_LOG_HMAC_KEY`
  no está definida, también cambia la clave de la cadena de auditoría. Conviene fijarla aparte
  antes de rotar.
- Claves de proveedores: basta con reiniciar la API (`docker compose restart backend`).

## 7. Pruebas y calidad

```bash
# Backend (desde backend/). Con TEST_DATABASE_URL corren también las pruebas que necesitan
# Postgres; la base debe tener «test» en el nombre porque se vacía en cada prueba.
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/dossier_test python -m pytest -q
python -m ruff check src/dossier
python -m mypy src/dossier
python -m pip_audit -r requirements.txt

# Frontend (desde frontend/)
npm run lint
npx tsc --noEmit
npm test
npm audit --omit=dev
```

- Las pruebas que dependen de un `.env` local con `DOSSIER_CHARGE_CREDITS=false` fallan a
  propósito: hay que correr la suite completa **sin** `backend/.env`, por ejemplo en una copia
  limpia del repositorio.
- Política de pruebas (unitarias, integración, estrés y seguridad por cambio):
  [`../dev/testing-policy.md`](../dev/testing-policy.md). Estado de la deuda técnica:
  [`../evidencias/fase2/deuda-final/README.md`](../evidencias/fase2/deuda-final/README.md).

## 8. Registro de decisiones técnicas

### 8.1 Decisiones de arquitectura (ADR)

| ADR | Decisión |
|---|---|
| [0001](../architecture/decisions/0001-linea-llm-canonica.md) | Línea de implementación LLM canónica |
| [0002](../architecture/decisions/0002-modelo-de-lenguaje.md) | Modelo de lenguaje para la síntesis ejecutiva (DeepSeek) |
| [0003](../architecture/decisions/0003-fuente-registros-europeos.md) | Registros europeos: Francia y Alemania |
| [0004](../architecture/decisions/0004-proveedor-noticias.md) | Prensa: GDELT y NewsAPI |
| [0005](../architecture/decisions/0005-proveedor-correo.md) | Correo transaccional por SMTP |
| [0006](../architecture/decisions/0006-protocolo-estados-progresivos.md) | Estados en vivo por SSE, no WebSockets |
| [0007](../architecture/decisions/0007-calendario-visual.md) | Calendario visual de reuniones |
| [0008](../architecture/decisions/0008-indicador-creditos-para-preparar.md) | Indicador «Créditos para preparar» |
| [0009](../architecture/decisions/0009-contrato-progreso-por-scopes.md) | Progreso por scopes con snapshot en el trabajo |

### 8.2 Decisiones de la Fase 2 sin ADR propio

Cada una tiene su especificación en `specs/proposals/` y su verificación en `specs/reports/`.

| Tema | Decisión | Tarea |
|---|---|---|
| Retención | 24 h fijas, contadas desde la reunión si es de calendario; borrado verificado y auditado | S6.5 |
| Correo | Un correo por reunión; tres intentos seguidos y luego cada 10 min hasta 1 h | S6.3, S6.4 |
| Acceso desde el correo | Enlace de un solo uso, 24 h, se gasta al pulsar «Ver dossier»; solo se guarda su SHA-256 | S6.2 |
| Notificaciones | Canal SSE asíncrono propio en vez de sondeo; reconexión con retroceso de 1 a 30 s | S5.2, S5.3 |
| Dossier por módulos | Secciones desde el JSON y el Markdown como respaldo; `modules` aditivo en la API | S5.5, S3.5, S3.6 |
| Dossiers a la vez | Tope por plan configurable por el admin de plataforma; 409, no 429 | UX-ADMIN-01 |
| Trabajos colgados | Latido y barrido; pasan a `failed` | BUG-2026-11-11-01 |
| Tolerancia a fallos | Sin síntesis: informe `partial`, sin cobro ni caché; el detalle técnico de los errores no sale del log | S7.2 |
| Empresas por la cola | `POST /dossiers/corporate/generate` con `async_mode`: trabajo `corporate_manual` con avance por agente; la ruta síncrona se conserva | Informe beta |
| Preferencias de notificación | `users.notify_email` (apaga el PDF automático) y `notify_browser` (aviso del sistema operativo); riesgo y resumen semanal «Próximamente» | Informe beta |
| Cambio de plan sin pago | Intencional para pruebas rápidas: el admin de la organización cambia el plan desde Configuración | Decisión de FD |
| Fuentes de noticias | Adaptadores enchufables descubiertos al arrancar; ajustes por fuente en el panel; claves solo en el entorno; extra de créditos solo si la fuente responde (lo suma el trigger); límite diario atómico; prensa también en personas | UX-ADMIN-02 |

## 9. Problemas conocidos

- **La CI de GitHub no corre** desde el 2026-11-07 (facturación de la cuenta). Hasta resolverlo,
  correr las suites a mano antes de integrar cambios.
- **Sin saldo en DeepSeek** no se genera ningún informe: los dossiers de empresa quedan
  `partial` y los de persona, `failed`.
- **Esquema en dos lugares:** Alembic y `schema_patches.py` al arrancar. Todo cambio de esquema va
  en los dos (las migraciones reutilizan las tuplas de los parches).
- **Límites de tasa en memoria:** con más de un proceso, cada uno cuenta por separado.
- **El plan se cambia sin pago, a propósito:** sirve para probar rápido cada plan. Para operar
  con clientes reales, `PATCH /organization/plan` debería quedar detrás de una pasarela de pago.
- Otros puntos de deuda: [`../evidencias/fase2/deuda-final/README.md`](../evidencias/fase2/deuda-final/README.md#deuda-que-queda).
