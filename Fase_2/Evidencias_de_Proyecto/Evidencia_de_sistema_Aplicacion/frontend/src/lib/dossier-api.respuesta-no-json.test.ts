import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DossierApiError,
  NON_JSON_RESPONSE_MESSAGE,
  fetchCalendarDiagnostico,
  fetchCalendarEventosPorIntervalo,
  fetchGoogleIntegrationStartAsJson,
  persistAuthToken,
} from "./dossier-api";

/**
 * Si el backend se está reiniciando, el proxy entrega `/api/*` al frontend y la respuesta
 * es la página 404 de Next.js. Ese HTML nunca debe llegar al usuario como mensaje de error.
 */
const PAGINA_404_NEXT =
  '<!DOCTYPE html><html lang="es" class="h-full antialiased"><head><meta charSet="utf-8"/>' +
  '<link rel="stylesheet" href="/_next/static/chunks/135lh9pbgp-3o.css"/></head><body>404</body></html>';

function html(status: number) {
  return Promise.resolve(new Response(PAGINA_404_NEXT, { status, headers: { "Content-Type": "text/html" } }));
}

async function errorDe(promesa: Promise<unknown>): Promise<DossierApiError> {
  try {
    await promesa;
  } catch (e) {
    expect(e).toBeInstanceOf(DossierApiError);
    return e as DossierApiError;
  }
  throw new Error("se esperaba un DossierApiError");
}

describe("respuesta que no es JSON", () => {
  beforeEach(() => persistAuthToken("jwt-de-prueba", true));
  afterEach(() => vi.unstubAllGlobals());

  const llamadas: [string, () => Promise<unknown>][] = [
    ["conectar Google", () => fetchGoogleIntegrationStartAsJson()],
    ["diagnóstico de calendario", () => fetchCalendarDiagnostico("google")],
    [
      "eventos del calendario",
      () =>
        fetchCalendarEventosPorIntervalo("google", {
          desde: "2026-10-05T00:00:00-03:00",
          hasta: "2026-10-12T00:00:00-03:00",
        }),
    ],
  ];

  it.each(llamadas)("%s: el mensaje es legible y no contiene HTML", async (_nombre, llamar) => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => html(502)));

    const err = await errorDe(llamar());

    expect(err.status).toBe(502);
    expect(err.message).toBe(NON_JSON_RESPONSE_MESSAGE);
    expect(err.message).not.toContain("<");
  });

  it("conserva el cuerpo original en `body` para depurar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => html(502)));

    const err = await errorDe(fetchCalendarDiagnostico("google"));

    expect((err.body as { raw?: string }).raw).toContain("<!DOCTYPE html>");
  });

  it("ninguna llamada del cliente copia el cuerpo crudo al mensaje", () => {
    const fuente = readFileSync(join(__dirname, "dossier-api.ts"), "utf8");
    expect(fuente).not.toMatch(/detail:\s*text\.slice/);
  });
});
