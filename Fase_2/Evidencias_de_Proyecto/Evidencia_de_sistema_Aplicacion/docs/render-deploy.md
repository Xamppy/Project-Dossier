# Desplegar la API en Render (migración desde Railway)

El **frontend** sigue en **Vercel**. La **API FastAPI** y **PostgreSQL** se mueven a **Render** (web) + **Neon** (base gratis).

## Resumen

| Pieza | Dónde | Coste |
|-------|--------|--------|
| Frontend Next.js | Vercel | Hobby / gratis |
| API FastAPI | Render Web Service | Plan **Free** (se duerme sin tráfico) |
| PostgreSQL | **Neon** | Free tier |

---

## Parte 1 — Base de datos en Neon

1. Crear cuenta en [https://neon.tech](https://neon.tech).
2. **New project** → región cercana (p. ej. US East).
3. Copiar la **connection string** (formato `postgresql://...` o `postgres://...`).  
   La API la convierte sola a `postgresql+psycopg://` (ver `backend/src/dossier/db/settings.py`).
4. En el **SQL Editor** de Neon, ejecutar **en este orden**:
   1. Esquema base: `backend/src/dossier/db/Migracion.md` (todo el SQL) o `docs/sql/schema_project_dossier.sql` si está actualizado.
   2. Parches incrementales: **`docs/sql/patch_after_migracion_v1.sql`** (columnas que el código usa y no están en Migracion.md, p. ej. `dossiers.dossier_folder_id`).
5. Si teníais datos en Railway y aún podéis entrar: exportar con `pg_dump` e importar en Neon.  
   Si el trial ya venció, empezad con BD vacía y esquema SQL.

---

## Parte 2 — API en Render

### Opción A — Blueprint (recomendada)

1. [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**.
2. Conectar el repo **SistemaDossier** (GitHub).
3. Render detecta `render.yaml` en la raíz.
4. Tras crear el servicio, ir a **Environment** y añadir variables (ver lista abajo).
5. Pegar **`DATABASE_URL`** = connection string de Neon.

### Opción B — Manual

1. **New** → **Web Service** → repo GitHub → rama `main`.
2. **Runtime:** Python 3. **Root Directory:** `backend`. Los comandos siguientes son relativos a esa carpeta.

3. **Build command:** `pip install -r requirements.txt`  
4. **Start command:**  
   `uvicorn dossier.api.app:app --host 0.0.0.0 --port $PORT`  
5. **Environment:**
   - `PYTHON_VERSION` = `3.12.8`
   - `PYTHONPATH` = `src`
6. **Health check path:** `/health`

### Variables de entorno en Render (copiar desde Railway)

Obligatorias para el dashboard:

| Variable | Notas |
|----------|--------|
| `DATABASE_URL` | Connection string de Neon |
| `JWT_SECRET` | Mín. 16 caracteres; **mismo valor** que antes si queréis tokens válidos |
| `CORS_ORIGINS` | URL(s) de Vercel + `http://localhost:3000` |
| `FRONTEND_URL` | URL del front en Vercel (sin barra final), p. ej. `https://tu-app.vercel.app` |

OAuth / calendario:

| Variable |
|----------|
| `GOOGLE_CLIENT_ID` |
| `GOOGLE_CLIENT_SECRET` |
| `GOOGLE_REDIRECT_URI` |
| `MICROSOFT_CLIENT_ID` |
| `MICROSOFT_CLIENT_SECRET` |
| `MICROSOFT_TENANT_ID` |
| `MICROSOFT_REDIRECT_URI` |

APIs / IA (según uso):

| Variable |
|----------|
| `GEMINI_API_KEY` |
| `DEEPSEEK_API_KEY` |
| `PDL_API_KEY` |
| `COMPANIES_HOUSE_API_KEY` |
| `OPENAI_API_KEY` (opcional, solo con `DOSSIER_LEGACY_OPENAI=1`) |

Opcional:

| Variable | Valor sugerido |
|----------|----------------|
| `DATABASE_AUTO_CREATE_TABLES` | `0` (si ya aplicaste el SQL en Neon) |
| `CORS_ALLOW_VERCEL_APP_REGEX` | `1` (acepta previews `*.vercel.app`) |

**Importante:** `GOOGLE_REDIRECT_URI` y `MICROSOFT_REDIRECT_URI` deben usar la **URL pública de Render**, no Railway:

```text
https://sistemadossier-api.onrender.com/callback-google
https://sistemadossier-api.onrender.com/callback
```

(Sustituid por la URL real que os asigne Render; suele ser `https://<nombre-servicio>.onrender.com`.)

---

## Parte 3 — Vercel (frontend)

1. **Settings → Environment Variables**
   - `NEXT_PUBLIC_API_URL` = `https://<tu-servicio>.onrender.com` (sin barra final).
2. **Redeploy** del frontend.

Ver también [vercel-frontend.md](vercel-frontend.md).

---

## Parte 4 — Google Cloud y Azure

Añadir las **nuevas** redirect URIs (mantened las locales si seguís probando en local):

**Google Cloud** → OAuth client → Authorized redirect URIs:

- `https://<tu-servicio>.onrender.com/callback-google`
- `http://127.0.0.1:8000/callback-google` (local)
- `http://localhost:8000/callback-google` (local)

**Azure** → App registration → Redirect URIs:

- `https://<tu-servicio>.onrender.com/callback`

Actualizar en Render las variables `GOOGLE_REDIRECT_URI` y `MICROSOFT_REDIRECT_URI` con esas URLs HTTPS.

---

## Parte 5 — Comprobar

1. `https://<tu-servicio>.onrender.com/health` → `{"status":"ok",...}`
2. `https://<tu-servicio>.onrender.com/db/health` → `postgresql: ok`
3. Desde Vercel: registro / login.
4. Conectar Google / Outlook y listar eventos.

**Plan Free de Render:** el servicio **se duerme** tras ~15 min sin tráfico; la primera petición puede tardar **30–60 s** (cold start). Para demos, abrid `/health` unos segundos antes.

---

## Qué dejar de usar

- Servicios y Postgres en **Railway** (cuando hayáis migrado datos y probado Render).
- URLs `*.up.railway.app` en Vercel, Google y Azure.

No hace falta `mise.toml` en Render (solo era para el builder de Railway).
