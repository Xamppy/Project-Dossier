# Pruebas de carga con k6

Requiere [k6](https://k6.io/docs/get-started/installation/) y una API en marcha con PostgreSQL.

## Variables

| Variable | Descripción |
|----------|-------------|
| `BASE_URL` | API (default `http://127.0.0.1:8000`) |
| `K6_AUTH_TOKEN` | JWT de usuario `admin` o `user` |
| `K6_SCENARIO` | `dedup`, `credits` o `both` (default) |
| `K6_DEDUP_SUFFIX` | Sufijo fijo para escenario C (mismo nombre → dedup) |

## Escenarios

- **C — dedup async:** 10 requests simultáneos con el mismo nombre; debe devolver el mismo `job_id`.
- **E — créditos límite:** varias generaciones sync; con saldo agotado esperar HTTP 402.

## Ejemplos

```powershell
cd c:\Users\franc\Documents\SistemaDossier
$env:K6_AUTH_TOKEN = "<jwt>"
k6 run scripts/load/k6-dossier-saturation.js

k6 run -e K6_SCENARIO=dedup scripts/load/k6-dossier-saturation.js
k6 run -e K6_SCENARIO=credits scripts/load/k6-dossier-saturation.js
```

## Endpoints legacy

Por defecto `GET /generar-dossier` y `POST /calendario/generar-dossier-google` responden **404**.
Para desarrollo local: `DOSSIER_ENABLE_LEGACY_OPEN_ROUTES=1` en `.env`.
