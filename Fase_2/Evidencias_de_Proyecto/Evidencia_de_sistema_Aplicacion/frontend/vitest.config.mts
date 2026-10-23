import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// Vitest, no Jest: Next.js 16 usa ESM y Vitest lo entiende sin configuración
// extra. El objetivo es que `npm test` arranque en menos de un segundo, porque
// una suite lenta es una suite que nadie ejecuta mientras desarrolla.

// Node 25+ trae un `localStorage` global propio (Web Storage nativo). Sin
// `--localstorage-file` es un getter que devuelve undefined y tapa al de jsdom,
// así que todas las pruebas que tocan localStorage fallan. Se desactiva en los
// procesos hijos que lanza Vitest, no con NODE_OPTIONS en package.json: así
// funcionan igual `npx vitest`, `npm test` y scripts/qa.py, en Windows sin
// cross-env. Es condicional porque Node 20 no conoce la opción y aborta con
// «bad option»; allowedNodeEnvironmentFlags pregunta al propio binario en vez de
// adivinar por número de versión.
const sinWebStorageNativo = process.allowedNodeEnvironmentFlags.has(
  "--no-experimental-webstorage",
)
  ? ["--no-experimental-webstorage"]
  : [];

export default defineConfig({
  plugins: [react()],
  test: {
    // Explícito: execArgv solo se aplica a procesos hijos (forks), no a hilos.
    pool: "forks",
    poolOptions: {
      forks: { execArgv: sinWebStorageNativo },
    },
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["node_modules", ".next", "out"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.{test,spec}.{ts,tsx}",
        "src/i18n/messages/**", // catálogos de traducción, no lógica
        "src/**/*.d.ts",
      ],
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
