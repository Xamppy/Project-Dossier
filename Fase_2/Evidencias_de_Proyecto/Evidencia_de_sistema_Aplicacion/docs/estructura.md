# Estructura del repositorio SistemaDossier

El repositorio contiene dos aplicaciones: `frontend/` (Next.js) y `backend/` (FastAPI). Cada una conserva sus dependencias, configuración y comandos de desarrollo.

```text
SistemaDossier/
├── frontend/
│   ├── src/                 # app, components, hooks, providers, lib, i18n
│   ├── public/
│   ├── scripts/             # Traducciones y overlays
│   ├── package.json
│   ├── package-lock.json
│   ├── .env.local.example
│   └── vercel.json
├── backend/
│   ├── src/dossier/         # Paquete Python; módulos existentes conservados
│   ├── tests/               # pytest; incluye comprobación de i18n del frontend
│   ├── scripts/             # CLIs y mantenimiento de base de datos
│   ├── data/                # Salidas generadas, ignoradas por Git
│   ├── main.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pytest.ini
│   └── .env.example
├── docs/                    # Guías y SQL existente
├── scripts/load/            # Pruebas de carga del sistema
├── render.yaml              # Servicio con rootDir: backend
├── .gitignore
└── README.md
```

## Desarrollo local

Desde la raíz del repositorio, en una terminal:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python main.py
```

En Windows, activar con `.venv\Scripts\activate` y copiar con `copy`.

En otra terminal, desde la raíz:

```sh
cd frontend
npm ci
cp .env.local.example .env.local
npm run dev
```

Las credenciales de la API se configuran en `backend/.env`; la URL pública de la API en `frontend/.env.local`.

## Verificación

- Backend: ejecutar `python -m pytest` desde `backend/`.
- Frontend: ejecutar `npm run lint` y `npm run build` desde `frontend/`.
- Traducciones: ejecutar `node scripts/sync-i18n-keys.mjs`, `node scripts/apply-i18n-overlays.mjs` o `node scripts/export-missing-i18n.mjs` desde `frontend/`.
- Las CLIs y scripts Python se ejecutan desde `backend/`, por ejemplo `python scripts/sec_edgar.py`.

`main.py` incorpora `backend/src/` al path. Para Uvicorn directamente, usar `PYTHONPATH=src uvicorn dossier.api.app:app --reload` desde `backend/`.

## Despliegue y base de datos

- Render: conservar `render.yaml` en la raíz; el servicio usa `rootDir: backend`. En servicios configurados manualmente, ajustar Root Directory a `backend`.
- Vercel: ajustar Root Directory a `frontend`.
- SQL: permanece en `docs/`, y el DDL existente en `backend/src/dossier/db/Migracion.md`. Su unificación corresponde a una etapa posterior.
- `dossier.config.PROJECT_ROOT` apunta a `backend/`; `DOCS_DIR` apunta a `docs/` en la raíz del repositorio.

Guías: [Render](render-deploy.md), [Vercel](vercel-frontend.md), [PostgreSQL](postgresql.md), [autenticación](auth-app.md), [calendario OAuth](calendario-oauth-operaciones.md).
