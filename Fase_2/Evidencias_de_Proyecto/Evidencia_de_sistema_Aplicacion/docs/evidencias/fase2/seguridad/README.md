# Evidencias de seguridad · Fase 2 (OE8)

Evidencias del objetivo específico 8: controles de acceso, limitación de tasa y registro de
auditoría, validados con pruebas automatizadas. Son salidas y capturas reales, sin retoques.

> **Ambiente local de pruebas, datos ficticios.** Ninguna evidencia muestra datos de personas o
> empresas reales, cuentas reales ni credenciales.

## Cómo se obtuvieron

| | |
|---|---|
| **Fecha** | 2026-11-07 |
| **Código** | rama `docmac` en `a5a8add` (merge de `main` con el correo, S6.1), sin cambios locales en el código |
| **Base de datos** | PostgreSQL 18 desechable, iniciado con `initdb` en una carpeta temporal, puerto 55432, bases `dossier_evid_seg_test` y `dossier_evid_ui_test`, borradas al terminar |
| **Backend** | API FastAPI real del repositorio en `127.0.0.1:8030`, con los trabajadores apagados. Variables definidas: `DATABASE_URL`, `JWT_SECRET` y `AUDIT_LOG_HMAC_KEY` de prueba, `CORS_ORIGINS=http://localhost:3040` y `CORS_ALLOW_VERCEL_APP_REGEX=0` |
| **Frontend** | `next dev` del repositorio en `localhost:3040`, con `NEXT_PUBLIC_API_URL=http://127.0.0.1:8030` |
| **Navegador** | Chrome sin interfaz, controlado por DevTools Protocol, a 1440 × 900 px |

## Evidencias

| Archivo | Qué muestra |
|---|---|
| [`01-pytest-seguridad-con-postgres.txt`](01-pytest-seguridad-con-postgres.txt) · [png](01-pytest-seguridad-con-postgres.png) | `pytest tests/security -v` contra PostgreSQL real: **159 passed, 3 skipped**. El PNG muestra las pruebas de auditoría (S4.10), CORS (S3.8), límite de tasa (S5.8) y tokens de renovación (S3.9); el `.txt` tiene las 162. Las 3 saltadas esperan tareas pendientes: S6.6 y S6.5 (retención de 24 h) |
| [`01b-pytest-seguridad-por-archivo.txt`](01b-pytest-seguridad-por-archivo.txt) · [png](01b-pytest-seguridad-por-archivo.png) | La misma suite con la salida normal de pytest: una línea por archivo (21 archivos), **159 passed, 3 skipped**. Es la figura 18 del informe final, porque se lee mejor a ese tamaño |
| [`02-login-limite-de-intentos.png`](02-login-limite-de-intentos.png) | Pantalla de inicio de sesión tras seis intentos fallidos seguidos con la cuenta ficticia `analista.demo@consultora-demo.example.org`. Los cinco primeros responden «Email o contraseña incorrectos» (HTTP 401); el sexto, «Demasiados intentos. Espera 288 segundos y vuelve a intentarlo» (HTTP 429, `LOGIN_FAILURE_RATE_LIMIT` = 5 fallos cada 300 s por correo). La figura 19 del informe final es un recorte de esta captura al formulario, sin otros retoques |

Registro de la API durante la captura 02:

```
"POST /auth/login HTTP/1.1" 401 Unauthorized   (× 5)
"POST /auth/login HTTP/1.1" 429 Too Many Requests
```
