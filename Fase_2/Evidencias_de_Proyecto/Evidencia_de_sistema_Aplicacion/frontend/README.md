# Frontend de Sistema Dossier

Dashboard con Next.js, React y TypeScript. La API FastAPI está en `../backend/`.

## Desarrollo

Ejecutar desde esta carpeta:

```sh
npm ci
cp .env.local.example .env.local
npm run dev
```

En Windows, usar `copy .env.local.example .env.local`.
Configurar `NEXT_PUBLIC_API_URL` en `.env.local` y arrancar la API desde `backend/`.
Abrir http://localhost:3000.

## Comandos

- `npm run build`: compilar para producción; las fuentes Inter y Space Mono requieren acceso a Google Fonts.
- `npm start`: servir la compilación de producción.
- `npm run lint`: revisar el código con ESLint.
- `npm test`: correr las pruebas con Vitest. Funciona en Node 20, 22 y 26 sin variables de entorno; en Node 25+ `vitest.config.mts` desactiva el `localStorage` nativo de Node para que no tape al de jsdom.
- `node scripts/export-missing-i18n.mjs`: exportar traducciones faltantes.
- `node scripts/sync-i18n-keys.mjs`: sincronizar claves de traducción.
- `node scripts/apply-i18n-overlays.mjs`: aplicar overlays de traducciones.

Las rutas están en `src/app/`, los componentes en `src/components/` y el cliente de la API en `src/lib/dossier-api.ts`.

## Despliegue

En Vercel, configurar **Root Directory** como `frontend` y definir `NEXT_PUBLIC_API_URL` con la URL del backend.
Ver [la guía de Vercel](../docs/vercel-frontend.md) y [la estructura del repositorio](../docs/estructura.md).
