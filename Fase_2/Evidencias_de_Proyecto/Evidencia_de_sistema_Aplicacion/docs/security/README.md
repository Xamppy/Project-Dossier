# Seguridad

Estado verificado el **07-09-2026**. Este archivo se actualiza a medida que las tareas del
objetivo OE8 se van cerrando.

## Estado de los cuatro controles comprometidos

El objetivo específico 8 compromete cuatro controles. **Solo uno existe.**

| Control | Estado | Tarea | Evidencia |
|---|---|---|---|
| Control de acceso | **implementado** | — | JWT firmado, RBAC con roles admin/user/viewer, aislamiento por organización, pruebas en `test_rbac.py` |
| Limitación de tasa | **ausente** | S5.8 | No hay slowapi ni middleware equivalente |
| Registro de auditoría | **ausente** | S4.10, S6.6 | No hay tabla ni servicio |
| Retención de 24 h con borrado verificado | **diverge** | S6.5 | Hoy 7 a 90 días, sin verificación de borrado |

## Hallazgos abiertos

### Retención por debajo de lo exigido

`backend/src/dossier/services/dossier_retention.py`

```python
ALLOWED_DOSSIER_RETENTION_DAYS = frozenset({7, 14, 30, 90})
DEFAULT_DOSSIER_RETENTION_DAYS = 30
```

`None` significa conservar indefinidamente. La especificación exige **24 horas con borrado
verificado**. Hoy el mínimo es 7 días y el borrado no se verifica: solo se ejecuta.

**Cierra en:** S6.5.

### Sin rastro de acceso a datos personales

El sistema trata datos de personas identificables (PDL, Lusha, registros corporativos, prensa)
y no registra quién accedió a qué. Las coincidencias de «audit» en el código son texto de
instrucciones al modelo y un comentario.

**Cierra en:** S4.10, y se extiende en S6.6 a envíos de correo y borrados por retención.

### Rutas legadas

`backend/src/dossier/security/legacy_routes.py` con `assert_legacy_route_allowed()`, controlado
por `DOSSIER_ENABLE_LEGACY_OPEN_ROUTES`. Están bien acotadas y hay prueba
(`test_legacy_routes.py`), pero deben retirarse.

**Cierra en:** S1.6. Mantén la variable apagada mientras tanto.

## Hallazgos cerrados

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

Pruebas de seguridad y aislamiento: **S6.7** y **S6.8**. Hasta entonces, lo único que cubre este
frente es `test_rbac.py`.

Auditoría de dependencias (pendiente de S0.3 y S1.4):

```bash
cd backend  && pip-audit
cd frontend && npm audit
```
