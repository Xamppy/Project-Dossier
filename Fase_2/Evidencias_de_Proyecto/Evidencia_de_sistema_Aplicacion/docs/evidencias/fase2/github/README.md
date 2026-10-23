# Evidencia: GitHub del repositorio

Capturas de la interfaz web de [`Xamppy/Project-Dossier`](https://github.com/Xamppy/Project-Dossier), el
repositorio de trabajo, que es público desde el 22-10-2026. Muestran lo que ve cualquier evaluador sin
cuenta.

**Cómo se tomaron:** el **22-10-2026**, con Chrome DevTools (MCP) en un contexto aislado y **sin sesión
iniciada** (la página muestra «Sign in» y «Sign up»), ventana de 1440×900. No se hizo clic en nada que
cambiara el repositorio. Las capturas 01, 07 y 08 son de página completa; las demás, de la parte visible.
`main` estaba en `ee6a512`, el merge del PR #39.

Hasta el 19-10-2026 el repositorio era privado y las capturas de esta carpeta se tomaron en la copia
pública `Xamppy/Project-Dossier-public` (ver `docs/dev/repo-publico.md`). Esas versiones siguen en el
historial de git (commit `c955d51`).

| Archivo | Qué muestra | URL | Fecha | Criterio que respalda |
|---|---|---|---|---|
| [01-repositorio-publico.png](01-repositorio-publico.png) | Portada del repositorio: etiqueta *Public*, 34 ramas, 209 commits, el último con check verde, árbol de carpetas y el README completo | https://github.com/Xamppy/Project-Dossier | 22-10-2026 | Documentación; uso de Git |
| [02-actions.png](02-actions.png) | Lista de ejecuciones de Actions (111 en total). Las de «Imágenes Docker» con ícono de cancelada las detuvo `concurrency: cancel-in-progress` de `imagenes.yml` al llegar un push más reciente | https://github.com/Xamppy/Project-Dossier/actions | 22-10-2026 | CI |
| [03-ci-ejecucion-exitosa.png](03-ci-ejecucion-exitosa.png) | Detalle de la CI #75 sobre `main` (push de `ee6a512`): estado *Success*, jobs Backend (pytest, ruff, mypy) y Frontend (eslint, vitest, build) en verde, 2m 41s | https://github.com/Xamppy/Project-Dossier/actions/runs/39872553288 | 22-10-2026 | CI |
| [03b-ci-job-backend-pasos.png](03b-ci-job-backend-pasos.png) | Job Backend de la CI #75 con sus pasos en verde: checkout fijado por SHA, instalar Python y dependencias, ruff, mypy y pytest con cobertura | https://github.com/Xamppy/Project-Dossier/actions/runs/39872553288/job/120150230746 | 22-10-2026 | CI |
| [04-migraciones-alembic.png](04-migraciones-alembic.png) | Las 3 revisiones de Alembic en `backend/alembic/versions`, con el commit que agregó cada una | https://github.com/Xamppy/Project-Dossier/tree/main/backend/alembic/versions | 22-10-2026 | Migraciones |
| [05-evidencias-fase2.png](05-evidencias-fase2.png) | La carpeta `docs/evidencias/fase2` publicada: CI/CD, migraciones, almacenamiento, pruebas, calidad, contribuciones, GitHub e interfaz | https://github.com/Xamppy/Project-Dossier/tree/main/docs/evidencias/fase2 | 22-10-2026 | Documentación |
| [06-commits.png](06-commits.png) | Historial de `main` con commits convencionales (`chore(harness)`, merges de los PR #21, #27, #28, #29 y #39) | https://github.com/Xamppy/Project-Dossier/commits/main | 22-10-2026 | Uso de Git |
| [07-contribuidores.png](07-contribuidores.png) | Gráfico de contribuidores de los últimos 3 meses, sin merges: Xamppy 91 commits, darygod 55, fedocmac 12 (ver nota) | https://github.com/Xamppy/Project-Dossier/graphs/contributors | 22-10-2026 | Aporte por integrante |
| [08-workflow-ci.png](08-workflow-ci.png) | El archivo `.github/workflows/ci.yml` completo: disparadores en push y PR a `main`, acciones fijadas por SHA y los pasos de los dos jobs | https://github.com/Xamppy/Project-Dossier/blob/main/.github/workflows/ci.yml | 22-10-2026 | CI |
| [09-adr.png](09-adr.png) | Los 9 registros de decisiones de arquitectura (ADR 0001 a 0009) en `docs/architecture/decisions` | https://github.com/Xamppy/Project-Dossier/tree/main/docs/architecture/decisions | 22-10-2026 | Documentación |

## Notas

- **Contribuidores.** GitHub muestra también a `claude` (147 commits) porque cuenta como contribuidor a
  cada coautor declarado con `Co-Authored-By`. Esos commits ya figuran a nombre de un integrante; no es una
  quinta persona. La correspondencia es Xamppy = FO, darygod = DG y fedocmac = FD. Los 91 commits de FO
  son los 72 de [contribuciones/](../contribuciones/README.md), medidos el 19-10-2026, más los 19 del
  20-10-2026 al 22-10-2026 (correcciones de los PR #17–#29 y el cierre del harness).
- **Registros de las ejecuciones.** Sin sesión, GitHub muestra los jobs y sus pasos, pero no el texto de
  los registros («Sign in to view logs»). El texto completo de una ejecución equivalente está en
  [ci-cd/](../ci-cd/README.md).
- **Anotaciones de la CI #75.** Una advertencia de eslint en `frontend/src/app/register/page.test.tsx`
  (`'t' is assigned a value but never used`) y avisos de GitHub sobre la migración de `ubuntu-latest`.
  Ninguna hace fallar la ejecución.
