import type { TranslateFn } from "@/i18n";
import type { TranslationKey } from "@/i18n/types";

const EXACT_LEGACY: Record<string, TranslationKey> = {
  "PDL encontró perfil (sin LinkedIn en respuesta).": "detail.warn_pdl_profile_no_linkedin",
  "PDL respondió 429 (límite de tasa). Espera y reintenta.": "detail.warn_pdl_rate_limit",
  "Límite de solicitudes alcanzado. Espera un momento y reintenta.": "detail.warn_pdl_rate_limit",
  "No se encontró perfil verificable. Prueba email corporativo, LinkedIn o acrónimo de empresa.":
    "detail.warn_pdl_no_profile",
  "No se encontró información adicional sobre esta persona. Añade más información o revisa que el nombre completo sea correcto para mayor exactitud.":
    "detail.warn_pdl_no_profile",
  "PDL incluye email/teléfono en el match cuando existen; no hay paso «reveal» aparte.":
    "detail.warn_pdl_contact_in_match",
  "El email y teléfono se incluyen en el match cuando existen; no hay paso «reveal» aparte.":
    "detail.warn_pdl_contact_in_match",
};

/** Avisos informativos de PDL (no críticos para jobs parciales). */
export function isPdlProfileFoundInfoWarning(warning: string): boolean {
  const w = warning.trim();
  return /^PDL encontró perfil/i.test(w) || /^PDL found a profile/i.test(w);
}

export function translatePdlWarning(warning: string, t: TranslateFn): string {
  const w = warning.trim();
  if (!w) return w;

  const exact = EXACT_LEGACY[w];
  if (exact) return t(exact);

  const linkedinEs = w.match(/^PDL encontró perfil \(LinkedIn:\s*(.+?)\)\.?$/i);
  if (linkedinEs) {
    return t("detail.warn_pdl_profile_linkedin", { linkedin: linkedinEs[1].trim() });
  }

  const linkedinEn = w.match(/^PDL found a profile \(LinkedIn:\s*(.+?)\)\.?$/i);
  if (linkedinEn) {
    return t("detail.warn_pdl_profile_linkedin", { linkedin: linkedinEn[1].trim() });
  }

  if (w.startsWith("PDL respondió 401:") || w.startsWith("PDL HTTP 401")) {
    return t("detail.warn_pdl_auth");
  }
  if (w.startsWith("PDL respondió 402:") || w.startsWith("PDL HTTP 402")) {
    return t("detail.warn_pdl_credits");
  }

  return w;
}
