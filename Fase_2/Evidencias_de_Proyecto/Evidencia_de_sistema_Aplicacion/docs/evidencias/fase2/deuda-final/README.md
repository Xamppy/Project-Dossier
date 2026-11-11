# Deuda técnica final comparada con la línea base (S7.5)

Medido el **2026-11-10** sobre el commit `80f074d` (rama `feat/S7.5-deuda-tecnica-final`, igual a
`docmac` con S6.2–S6.6, BUG-08 y BUG-10). La línea base es la del diagnóstico del Sprint 0
(**S0.3, 2026-09-23**); la columna intermedia es la evidencia de `../calidad/` (**2026-10-19**).

El backend se midió en una copia limpia del repositorio, **sin** el `backend/.env` local (que apaga
el cobro de créditos para demos), con PostgreSQL 18 en `TEST_DATABASE_URL`. El frontend, en la
copia de trabajo, idéntica al commit.

## Resultado

| Indicador | Línea base (S0.3, 23-09) | Intermedio (19-10) | Final (10-11) | Evidencia |
|---|---|---|---|---|
| Pruebas del backend | 130 (113 en verde, **4 en rojo**, 13 en espera) | 768 en verde | **1.618 en verde**, 0 en rojo, 2 omitidas | [01](01-pytest-cobertura.txt) · [png](01-pytest-cobertura.png) |
| Cobertura del backend | **33 %** | 63 % | **72 %** (12.020 líneas, 3.307 sin cubrir) | [01](01-pytest-cobertura.txt) |
| ruff en `src/dossier` | **192 errores** | 0 | **0** | [02](02-ruff.txt) · [png](02-ruff.png) |
| mypy en `src/dossier` | **~45 errores** en 14 archivos | 0 en 124 archivos | **0 en 140 archivos** | [03](03-mypy.txt) · [png](03-mypy.png) |
| pip-audit (backend) | 0 | 2 en `pyjwt 2.14.0` | **0** | [04](04-pip-audit.txt) · [png](04-pip-audit.png) |
| eslint (frontend) | **21 errores** (07-09) | 0 errores, 1 advertencia | **0 errores**, 1 advertencia | [05](05-eslint.txt) · [png](05-eslint.png) |
| `tsc --noEmit` | — | 0 | **0** | [06](06-tsc.txt) · [png](06-tsc.png) |
| Pruebas del frontend | — (no corrían) | — | **653 en verde** (49 archivos) | [07](07-vitest-cobertura.txt) · [png](07-vitest-cobertura.png) |
| Cobertura del frontend | — | — | **41 %** de líneas (79 % de ramas) | [07](07-vitest-cobertura.txt) |
| npm audit (producción) | **3 críticas** en `next 16.2.6` | 6 (5 altas, 1 moderada) | **0** | [08](08-npm-audit.txt) · [png](08-npm-audit.png) |
| Migraciones versionadas | no existían | Alembic | **8 revisiones** | `backend/alembic/versions/` |
| Integración continua | no existía | pruebas + análisis en cada cambio | existe, **pero sin correr desde el 07-11** | ver «Deuda que queda» |

**Lectura:** el código de la aplicación cerró la deuda que se midió al inicio. No queda ningún error
de análisis estático, ninguna vulnerabilidad conocida en las dependencias de producción y ninguna
prueba en rojo. La cobertura del backend se duplicó con creces (33 % → 72 %). Las pruebas pasaron
de 130 a más de 2.200 entre backend y frontend.

## Deuda que queda

Ordenada por impacto. Ninguna impide operar, pero conviene registrarla para la continuidad.

| # | Deuda | Impacto | Medición | Tarea |
|---|---|---|---|---|
| 1 | **La CI no corre** desde el 07-11-2026 (cuenta de GitHub bloqueada por facturación) | Ningún cambio se verifica en GitHub y el VPS no se actualiza solo | — | fuera del código |
| 2 | **La CI no tiene PostgreSQL**: omite las pruebas que lo necesitan | 315 de 1.620 pruebas del backend no corren en la CI | sin `TEST_DATABASE_URL`: 1.303 en verde, 317 omitidas | CHORE-2026-10-19-04 |
| 3 | **Módulos con poca cobertura**: integraciones externas y flujos de cuenta | Cambios ahí no tienen red de pruebas | `calendar_integrations` 12 %, `corporate_registry_context` 14 %, `account_service` 28 %, `org_invite_service` 31 %, `calendar_automation` 35 % | — |
| 4 | **Cobertura del frontend** baja en componentes de pantalla | Regresiones visuales sin detectar | 41 % de líneas | — |
| 5 | **24 hallazgos de ruff fuera de `src/dossier`** (scripts y pruebas; la CI no los revisa) | Estilo, no funcionamiento | `ruff check .`: 11 E402, 4 I001, 2 B017, 2 UP017, 2 C408 y otros | — |
| 6 | **Nombres engañosos con «gemini»** en 21 archivos que llaman a DeepSeek | Confunde a quien mantenga el código | `grep -ril gemini src/dossier` | — |
| 7 | **`users.dossier_retention_days` sin uso** desde S6.5 | Columna muerta en el esquema | — | limpieza |
| 8 | **Esquema en dos lugares**: Alembic y `schema_patches.py` al arrancar | Riesgo de que diverjan | — | — |
| 9 | **Límites de tasa en memoria** (S5.8) | Con más de un proceso, cada uno cuenta por separado | — | mover a Redis si se escala |
| 10 | **2 esqueletos de prueba omitidos** (S2.4 y S5.8), ya cubiertos por pruebas propias | Ruido en el resumen | `tests/stress/test_ejemplo_estres.py` | — |
| 11 | 1 advertencia de eslint (`t` sin usar en `register/page.test.tsx`) | Ninguno | — | — |

**Fuera del código:** la cuenta de DeepSeek de `backend/.env` no tiene saldo (error 402 en la
prueba de punta a punta del 10-11). Si el VPS usa la misma cuenta, la generación con IA falla.

## Cómo reproducir

```bash
# backend (copia limpia, sin .env; PostgreSQL de pruebas en TEST_DATABASE_URL)
python -m pytest -q --cov=src/dossier --cov-report=term
python -m ruff check src/dossier
python -m mypy src/dossier
python -m pip_audit -r requirements.txt --progress-spinner off
# frontend
npm run lint
npx tsc --noEmit
npm run test:cov
npm audit --omit=dev
```

Cada `.txt` guarda la salida literal con fecha, commit y código de salida; el `.png` la muestra
(o su final, si es larga, como se indica en su encabezado). Generados con
`../_herramientas/ev.py`.
