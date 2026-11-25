import { afterEach, describe, expect, it, vi } from "vitest";
import { createTranslator } from "@/i18n";
import de from "@/i18n/messages/de";
import en from "@/i18n/messages/en";
import es from "@/i18n/messages/es";
import fr from "@/i18n/messages/fr";
import it_ from "@/i18n/messages/it";
import pt from "@/i18n/messages/pt";
import type { TranslationKey } from "@/i18n/types";
import { personEnrichmentNotice } from "./person-enrichment-notice";
import { translateBackendWarning, translateDossierStatusMessage } from "./translate-backend-message";

// El aviso amarillo del detalle juntaba tres causas: modo sin registros, sin coincidencias y
// falla del proveedor. Cada una se trata aparte.

const SIN_COINCIDENCIAS =
  "No se encontró información adicional sobre esta persona. Añade más información o revisa que el nombre completo sea correcto para mayor exactitud.";

// Textos exactos de PDL_FAILURE_WARNINGS (backend/src/dossier/services/pdl_research.py).
const FALLAS: [TranslationKey, string][] = [
  [
    "detail.warn_pdl_auth",
    "No se pudo completar la consulta de registros de esta persona: el proveedor de datos rechazó el acceso. Avisa al administrador.",
  ],
  [
    "detail.warn_pdl_config",
    "No se pudo completar la consulta de registros de esta persona: el proveedor de datos no está configurado. Avisa al administrador.",
  ],
  [
    "detail.warn_pdl_credits",
    "No se pudo completar la consulta de registros de esta persona: se agotaron los créditos del proveedor de datos. Avisa al administrador.",
  ],
  [
    "detail.warn_pdl_rate_limit",
    "No se pudo completar la consulta de registros de esta persona: el proveedor de datos recibió demasiadas solicitudes. Espera un momento y vuelve a generar el dossier.",
  ],
  [
    "detail.warn_pdl_timeout",
    "No se pudo completar la consulta de registros de esta persona: el proveedor de datos tardó demasiado en responder. Vuelve a intentarlo más tarde.",
  ],
  [
    "detail.warn_pdl_error",
    "No se pudo completar la consulta de registros de esta persona: el proveedor de datos respondió con un error. Vuelve a intentarlo más tarde.",
  ],
];

// Avisos guardados en dossiers anteriores a este cambio.
const FALLAS_ANTERIORES: [TranslationKey, string][] = [
  ["detail.warn_pdl_config", "Falta PDL_API_KEY en el entorno (.env). Créala en People Data Labs → Dashboard → API Keys."],
  ["detail.warn_pdl_auth", "PDL respondió 401: revisa PDL_API_KEY en `.env`."],
  ["detail.warn_pdl_auth", "PDL (authentication_error): invalid key"],
  ["detail.warn_pdl_credits", "PDL (payment_required): You have hit your account maximum"],
  [
    "detail.warn_pdl_credits",
    "PDL: créditos de enriquecimiento agotados. Se intentó búsqueda alternativa; si no hay resultados, recarga créditos en tu cuenta PDL.",
  ],
  ["detail.warn_pdl_rate_limit", "Límite de solicitudes alcanzado. Espera un momento y reintenta."],
  ["detail.warn_pdl_error", "PDL HTTP 500: boom"],
];

const KEYS = FALLAS.map(([key]) => key);

afterEach(() => vi.restoreAllMocks());

describe("aviso de un dossier de persona sin perfiles", () => {
  it("no hay aviso en «Web pública», aunque el dossier guarde avisos antiguos", () => {
    expect(
      personEnrichmentNotice({ researchSource: "gemini_web", profilesCount: 0, warnings: [SIN_COINCIDENCIAS] }),
    ).toBeNull();
    expect(personEnrichmentNotice({ researchSource: "gemini_web", profilesCount: 0, warnings: [] })).toBeNull();
  });

  it("no hay aviso si PDL encontró perfiles o el dossier no lo registra", () => {
    expect(personEnrichmentNotice({ researchSource: "pdl", profilesCount: 1, warnings: [FALLAS[0][1]] })).toBeNull();
    expect(personEnrichmentNotice({ researchSource: "pdl", profilesCount: null, warnings: [] })).toBeNull();
  });

  it("sin coincidencias se mantiene el aviso de siempre", () => {
    for (const warnings of [[], [SIN_COINCIDENCIAS], ["La opción «incluir posts» no está disponible; se ignoró."]]) {
      expect(personEnrichmentNotice({ researchSource: "pdl", profilesCount: 0, warnings })).toBe(
        "detail.enrichment_no_profiles",
      );
    }
  });

  it.each([...FALLAS, ...FALLAS_ANTERIORES])("%s ← %s", (key, warning) => {
    expect(
      personEnrichmentNotice({ researchSource: "pdl", profilesCount: 0, warnings: ["otro aviso", warning] }),
    ).toBe(key);
  });

  it("un dossier antiguo sin tipo de investigación se trata como PDL", () => {
    expect(personEnrichmentNotice({ researchSource: null, profilesCount: 0, warnings: [] })).toBe(
      "detail.enrichment_no_profiles",
    );
  });
});

describe("textos de las fallas del proveedor", () => {
  it.each(Object.entries({ es, en, pt, it: it_, fr, de }) as [string, Record<string, string>][])(
    "%s los tiene todos, distintos y sin nombrar al proveedor",
    (_locale, messages) => {
      const textos = KEYS.map((key) => messages[key]);
      for (const texto of textos) {
        expect(texto).toBeTruthy();
        expect(texto).not.toMatch(/PDL|People Data Labs|40\d|429/);
      }
      expect(new Set(textos).size).toBe(KEYS.length);
    },
  );

  it.each(FALLAS)("en español %s no se pierde aunque coincida con el texto del servidor", (key, warning) => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const t = createTranslator("es");
    expect(translateBackendWarning(warning, t)).toBe(t(key));
    expect(translateDossierStatusMessage(warning, t)).toBe(t(key));
    expect(warn).not.toHaveBeenCalled();
  });
});
