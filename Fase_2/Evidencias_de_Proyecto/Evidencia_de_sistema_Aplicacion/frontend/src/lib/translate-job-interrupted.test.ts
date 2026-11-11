import { describe, expect, it } from "vitest";
import { createTranslator } from "@/i18n";
import { SUPPORTED_LOCALES } from "@/i18n/types";
import { translateDossierStatusMessage } from "@/lib/translate-backend-message";

// Un trabajo colgado tras una caída del servidor se marca como fallido con este mensaje.
const INTERRUMPIDO = "La generación se interrumpió porque el servidor se reinició. Vuelve a intentarlo.";

describe("trabajo interrumpido por un reinicio del servidor", () => {
  it.each(SUPPORTED_LOCALES)("se explica en %s", (locale) => {
    const t = createTranslator(locale);
    const texto = translateDossierStatusMessage(INTERRUMPIDO, t);
    expect(texto).toBe(t("backend.status_job_interrupted"));
    expect(texto).not.toBe("backend.status_job_interrupted");
    expect(texto).not.toBe(t("errors.server_generic"));
  });
});
