import type { TranslationKey } from "@/i18n/types";
import { pdlFailureKey } from "@/lib/translate-pdl-warning";

type Diagnostics = {
  researchSource: string | null;
  profilesCount: number | null;
  warnings: string[];
};

/**
 * Aviso del detalle de un dossier de persona sin perfiles, o `null` si no corresponde.
 *
 * «Web pública» nunca consulta PDL: 0 perfiles ahí no dice nada sobre la persona. Con PDL,
 * no encontrar a la persona y que el proveedor falle son avisos distintos.
 */
export function personEnrichmentNotice({ researchSource, profilesCount, warnings }: Diagnostics): TranslationKey | null {
  if (researchSource === "gemini_web" || profilesCount !== 0) return null;
  for (const warning of warnings) {
    const key = pdlFailureKey(warning);
    if (key) return key;
  }
  return "detail.enrichment_no_profiles";
}
