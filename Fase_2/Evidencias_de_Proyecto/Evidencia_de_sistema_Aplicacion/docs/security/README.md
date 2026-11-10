# Seguridad

Estado verificado el **10-11-2026**. Este archivo se actualiza a medida que las tareas del
objetivo OE8 se van cerrando.

## Estado de los cuatro controles comprometidos

El objetivo específico 8 compromete cuatro controles. Los cuatro existen; a la auditoría le falta
sumar correos y borrados (S6.6).

| Control | Estado | Tarea | Evidencia |
|---|---|---|---|
| Control de acceso | **implementado** | S6.7 verifica el aislamiento | JWT firmado, RBAC con roles admin/user/viewer, aislamiento por organización; pruebas en `test_rbac.py` y `test_aislamiento_organizaciones.py` |
| Limitación de tasa | **implementado** | S5.8 | 429 con `Retry-After` en autenticación y generación; ver «Sin limitación de tasa» |
| Registro de auditoría | **implementado** (lectura y generación) | S4.10; S6.6 suma correos y borrados por retención | `audit_logs` de solo inserción y firmada; ver «Sin rastro de acceso a datos personales» |
| Retención de 24 h con borrado verificado | **implementado** | S6.5 | Plazo fijo para todos los dossiers; ver «Retención de 24 horas» |

## Retención de 24 horas

Cerrada en S6.5 (`specs/proposals/S6.5-retencion-24h.md`). Antes, cada usuario elegía 7 a 90 días
o conservar indefinidamente, y el borrado no se verificaba.

- **Plazo fijo:** `DOSSIER_RETENTION_HOURS` (24 por omisión) para todos los dossiers. El usuario
  ya no elige; `users.dossier_retention_days` quedó sin uso.
- **Qué borra** `services/dossier_retention_worker.py`: cada dossier creado antes del corte, con
  sus alertas, prensa, registros, trayectoria, ice breakers y enlaces compartidos (por
  `ON DELETE CASCADE`) y su entrada de Redis; y los jobs de generación terminados antes del corte,
  que guardan el nombre consultado y el resultado. `credit_ledger` conserva el movimiento con
  `dossier_id` en `NULL`.
- **Verificación:** tras el `commit` vuelve a contar filas y claves de Redis. Sin restos registra
  «borrado verificado»; con restos, un `ERROR` con tabla y cantidad, nunca datos de la persona.
- **Atraso máximo:** el intervalo del worker, `DOSSIER_RETENTION_POLL_SECONDS` (600 s por omisión).
- **Caché:** el TTL de Redis nunca supera la retención.
- **Fuera del sistema:** el PDF que llega por correo (S6.1) es la copia del usuario y no se borra.

Pruebas: `tests/security/test_ejemplo_seguridad.py` (no recuperable y sin huérfanos),
`tests/integration/test_retencion_24h_integracion.py` y `tests/test_retencion_24h.py`.

## Hallazgos abiertos

### Rutas legadas

`backend/src/dossier/security/legacy_routes.py` con `assert_legacy_route_allowed()`, controlado
por `DOSSIER_ENABLE_LEGACY_OPEN_ROUTES`. Están bien acotadas y hay prueba
(`test_legacy_routes.py`), pero deben retirarse.

**Cierra en:** S1.6. Mantén la variable apagada mientras tanto.

## Hallazgos cerrados

### Sin limitación de tasa — cerrado en S5.8

Antes no había límite de peticiones: se podía probar contraseñas sin freno o disparar
generaciones de dossiers en ráfaga (créditos y cuota de proveedores externos).

Ahora (`security/rate_limit.py`, ventana deslizante en memoria; la API corre con un solo
proceso, `--workers 1`):

| Variable | Por omisión | Qué limita | Clave |
|---|---|---|---|
| `AUTH_RATE_LIMIT` | `20/60` | Inicio de sesión, registro, renovación, recuperación y Google | IP de la conexión |
| `LOGIN_FAILURE_RATE_LIMIT` | `5/300` | Inicios de sesión **fallidos** (uno correcto los limpia) | Hash del correo |
| `GENERATION_RATE_LIMIT` | `10/60` | Generación de dossiers (corporativo, personas y calendario) | Usuario del token (IP si no es válido) |

- Formato `N/S` (N peticiones cada S segundos) u `off`. Un valor inválido usa el de omisión.
- Al superarlo: **HTTP 429**, cabecera `Retry-After` y `detail.code = "rate_limited"`. El
  dashboard muestra cuántos segundos esperar (`errors.rate_limited`, 7 idiomas).
- Un rechazo no cuenta como petición. La IP sale de la conexión, no de `X-Forwarded-For`
  (detrás de Caddy la corrige uvicorn `--proxy-headers`). Las claves están acotadas en
  memoria aunque un atacante rote IPs.
- Con varios procesos habría que mover los contadores a Redis.

Pruebas: `tests/test_rate_limit.py`, `tests/integration/test_rate_limit_rutas.py`,
`tests/security/test_rate_limit_seguridad.py` y `tests/stress/test_rate_limit_estres.py`.

### Sin rastro de acceso a datos personales — cerrado en S4.10 (S6.6 lo extiende)

Antes, el sistema trataba datos de personas identificables (PDL, Lusha, registros
corporativos, prensa) sin registrar quién accedía a qué. La tabla `audit_logs` existía desde
la línea base (Migracion.md, sección 13) pero nadie la usaba.

Ahora, con el diseño de Migracion.md (WHO, WHAT, WHEN, WHERE, RESULT):

- **Toda lectura y generación de dossier** queda registrada por el middleware
  `api/audit_middleware.py`: listar y ver dossiers y carpetas, compartir, borrar, generar
  (corporativo, personas y calendario) y consultar los jobs. Acción = verbo + plantilla de la
  ruta (`GET /dossiers/{dossier_id}`); recurso = el id. **También los intentos fallidos**
  (401, 403, 404, 500), por ejemplo leer un dossier de otra organización.
- La generación en segundo plano también: el trabajador de la cola (`JOB person_manual`,
  `JOB calendar_manual`) y la automatización del calendario (`AUTO calendar_automation`).
- **Solo inserción**: el trigger `trg_audit_logs_inmutable` rechaza UPDATE y DELETE. Única
  excepción: la base deja en NULL el usuario o la organización al borrarlos (`ON DELETE SET
  NULL`), para no impedir el borrado de cuentas.
- **Firma**: `log_hash` es un HMAC-SHA256 con `AUDIT_LOG_HMAC_KEY` (o `JWT_SECRET`); una fila
  alterada sin la clave no verifica (`services/audit_log.verify_log_hash`).
- **Sin datos personales**: `request_data` guarda solo parámetros de consulta, con correos,
  nombres, teléfonos y tokens ocultos, e ids de los dossiers generados; nunca su contenido.
- Si escribir el registro falla, la respuesta al usuario no cambia (queda en el log).

Pruebas: `tests/test_audit_log.py`, `tests/integration/test_audit_log_flujo.py`,
`tests/integration/test_audit_log_migracion.py`, `tests/security/test_audit_log_seguridad.py`
y `tests/stress/test_audit_log_estres.py`.

**Pendiente en S6.6:** envíos de correo (depende de S6.1) y borrados por retención (S6.5).

### Token de acceso de 7 días en `localStorage` — cerrado en S3.9

Antes, el JWT de acceso duraba 7 días (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES=10080`) y se guardaba
en `localStorage`: un XSS podía llevarse una sesión de una semana.

Ahora:

- El token de acceso dura **15 minutos** (`security/jwt_tokens.py`).
- La sesión larga la sostiene un **token de renovación opaco** en la cookie `dossier_refresh`:
  `HttpOnly` (JavaScript no la lee), `Secure`, `SameSite=Strict` y `Path=/auth` (o `/api/auth`
  detrás de Caddy). Con «Recuérdame» dura `REFRESH_TOKEN_EXPIRE_DAYS` (30); sin él, 12 h y se
  pierde al cerrar el navegador (`api/refresh_cookie.py`).
- En la base solo se guarda el **hash SHA-256** (`refresh_tokens.token_hash`).
- `POST /auth/refresh` **rota** el token en cada uso y conserva el vencimiento original. Un token
  ya rotado que vuelve dentro de 30 s es una carrera entre pestañas (`refresh_rotated`); fuera de
  esa ventana es reutilización de un token robado y se **revocan todas** las sesiones del usuario
  (`refresh_reused`). Usuario desactivado o sin membresía: `refresh_inactive`
  (`security/refresh_tokens.py`).
- `POST /auth/logout` revoca el token y borra la cookie. Cambiar de organización mueve la sesión.
- El dashboard renueva solo ante un 401 y reintenta una vez (`authFetch` en
  `frontend/src/lib/dossier-api.ts`), también al reabrir el canal SSE.
- CORS permite credenciales solo para la lista explícita `CORS_ORIGINS`, nunca con la regla de
  `*.vercel.app` (`api/cors_config.py`).

Pruebas: `tests/test_refresh_tokens.py`, `tests/integration/test_refresh_tokens_flujo.py`,
`tests/integration/test_refresh_tokens_migracion.py`,
`tests/security/test_refresh_tokens_seguridad.py`, `tests/stress/test_refresh_tokens_estres.py`
y `frontend/src/lib/dossier-api.auth-refresh.test.ts`.

### CORS con métodos abiertos — cerrado en S3.8

Antes, `app.py` registraba `CORSMiddleware` con `allow_methods=["*"]`, `allow_headers=["*"]` y
`allow_credentials=True`, y aceptaba por omisión cualquier origen `https://*.vercel.app`, incluido
el de un tercero.

La política vive ahora en `backend/src/dossier/api/cors_config.py`:

- Métodos explícitos: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`.
- Cabeceras explícitas: `Authorization`, `Content-Type`, `Accept`, `Accept-Language`,
  `Last-Event-ID` (reanudación del canal SSE).
- `allow_credentials=False`: el dashboard autentica con `Authorization: Bearer`, no con cookies.
- `*.vercel.app` solo con `CORS_ALLOW_VERCEL_APP_REGEX=1` y con un patrón acotado
  (`https://[a-z0-9-]+\.vercel\.app`).

Pruebas: `tests/test_cors_config.py`, `tests/integration/test_cors_politica.py`,
`tests/security/test_cors_seguridad.py` y `tests/stress/test_cors_estres.py`.

## Reglas permanentes

1. **Credenciales solo en variables de entorno.** Nunca en el código, nunca en un commit. Si una
   credencial llega a un commit, hay que rotarla, no solo borrarla.
2. **Solo datos autorizados y ambientes de prueba.** Nunca datos reales de producción.
3. **Sin cobros reales.** Stripe únicamente en entorno de pruebas, y solo si S5.9 lo autoriza.
4. **`JWT_SECRET` de 16 caracteres como mínimo.** La API se niega a arrancar con menos
   (`assert_jwt_secret_configured`).
5. **Toda prueba de seguridad va a la CI.** Una regresión de seguridad debe bloquear la
   integración, no descubrirse en la defensa (S6.8).

## Verificación

### Aislamiento entre organizaciones (S6.7)

Pruebas negativas contra Postgres: no comprueban que algo funcione, sino que algo **no** sea
posible. Se ataca con el administrador de la organización A —si él no llega a B, nadie de A
llega— y se exige:

- **404 en todo id de B**, en las 13 rutas que reciben un id (dossier, carpeta, compartición,
  trabajo, canal de progreso, miembros, invitaciones), tanto al leer como al modificar o borrar.
- **La misma respuesta que un id inexistente**: la API no revela que el recurso existe en otra
  organización.
- **Ningún rastro de B** (ids, correos, sujeto, alertas, prensa, trayectoria) en ninguna
  respuesta ni en los listados de A, y **los datos de B intactos** después de cada intento.
- El `org_id` y el `role` del token no bastan: la base manda. Un token con la organización de B
  sin membresía es 403, un rol inflado no da permisos, y quien sale de la organización pierde el
  acceso aunque su token siga vigente.
- No se puede cambiar la sesión a una organización ajena, aceptar una invitación de otro correo ni
  compartir un dossier con alguien de otra organización.
- Quien pertenece a dos organizaciones solo ve la de su sesión activa.
- Las alertas, la prensa, la trayectoria y la auditoría no tienen ruta de lectura propia; si alguien
  agrega una, la prueba falla y obliga a cubrirla. El panel `/admin` es 403 para un admin de empresa.
- Bajo carga (24 hilos, 6 organizaciones) ninguna respuesta mezcla organizaciones.

Las pruebas se validaron rompiendo a propósito cada control (quitando el filtro por organización
uno a la vez): 7 de 8 cambios las hacen fallar. El octavo, quitar el filtro al borrar una carpeta,
no cambia nada porque el servicio vuelve a filtrar por organización (defensa doble).

Archivos: `backend/tests/security/test_aislamiento_organizaciones.py` y
`backend/tests/stress/test_aislamiento_organizaciones_estres.py`. Incorporarlas a la CI con
Postgres es **S6.8**.

Auditoría de dependencias (pendiente de S0.3 y S1.4):

```bash
cd backend  && pip-audit
cd frontend && npm audit
```
