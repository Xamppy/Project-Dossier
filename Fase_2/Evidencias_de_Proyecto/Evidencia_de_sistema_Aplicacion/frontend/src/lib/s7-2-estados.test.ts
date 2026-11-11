import { describe, expect, it } from "vitest";
import { createTranslator } from "@/i18n";
import { SUPPORTED_LOCALES } from "@/i18n/types";
import { formatDossierStatusLabel } from "@/lib/dossier-list-utils";
import { translateDossierStatusMessage } from "@/lib/translate-backend-message";

// S7.2: un dossier sin análisis con IA queda «parcial», y los mensajes de una fuente caída no
// llevan detalle técnico. Ambos se ven traducidos en los siete idiomas.
const PARCIAL =
  "Informe parcial: no se pudo redactar el análisis con IA; se muestran los datos reunidos de las fuentes.";
const PERSONA_SIN_FUENTES = "No se pudieron consultar las fuentes de esta persona. Vuelve a intentarlo más tarde.";

describe("S7.2 · estados y mensajes de tolerancia a fallos", () => {
  it.each(SUPPORTED_LOCALES)("%s nombra el estado parcial", (locale) => {
    const t = createTranslator(locale);
    expect(formatDossierStatusLabel("partial", t)).toBe(t("dossiers.status_partial"));
    expect(t("dossiers.status_partial")).not.toBe("dossiers.status_partial");
  });

  it.each(SUPPORTED_LOCALES)("%s traduce los mensajes de fuentes caídas", (locale) => {
    const t = createTranslator(locale);
    expect(translateDossierStatusMessage(PARCIAL, t)).toBe(t("backend.status_partial_report"));
    expect(translateDossierStatusMessage(PERSONA_SIN_FUENTES, t)).toBe(t("backend.status_person_sources_unavailable"));
    expect(t("backend.status_partial_report")).not.toBe("backend.status_partial_report");
  });
});
