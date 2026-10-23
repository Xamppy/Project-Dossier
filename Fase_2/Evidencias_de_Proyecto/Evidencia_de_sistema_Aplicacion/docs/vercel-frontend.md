# Desplegar el frontend (Next.js) en Vercel

El backend **FastAPI** debe ir en otro servicio (p. ej. **Render** o Railway). Vercel solo construye **`frontend`**. Guía API en producción: [render-deploy.md](render-deploy.md).

## Sobre el JSON “Welcome to the API!”

Ese mensaje **no está en este repositorio**. Si aparecía en la preview de Vercel, era por **detección errónea del proyecto como Python/FastAPI** (por ver `requirements.txt` / `main.py` en la raíz del monorepo). La solución es la configuración de abajo, **no** añadir ese JSON al código.

## Checklist en Vercel

1. **Settings → Build and Deployment**
   - **Root Directory:** `frontend`
   - **Framework Preset:** **Next.js**
   - **Include files outside the root directory in the Build Step:** **OFF**

2. **Settings → Environment Variables**
   - `NEXT_PUBLIC_API_URL` = URL HTTPS de tu API (Render), p. ej. `https://sistemadossier-api.onrender.com` (sin barra final).

3. **Backend (Render u otro): variable `CORS_ORIGINS`**

   Incluye el origen del front en producción, por ejemplo:

   `https://tu-proyecto.vercel.app,https://tu-proyecto-xxx.vercel.app,http://localhost:3000`

   Sin esto, el navegador bloqueará las llamadas desde el dominio de Vercel.

4. Tras cambiar ajustes o variables, **nuevo despliegue** (push a `main` o *Create deployment* con rama `main`, **sin** pegar la URL completa de GitHub en el campo de rama).

## Archivo `frontend/vercel.json`

Fija **Next.js** y `npm install` / `npm run build` para reducir ambigüedad en monorepos.

## Buscar texto dentro del código en GitHub

La caja “Ir al archivo” solo busca **nombres de archivos**. Para buscar **contenido**:

`repo:mmmbeke/SistemaDossier "texto"`

(sustituye el usuario/repo si difiere).
