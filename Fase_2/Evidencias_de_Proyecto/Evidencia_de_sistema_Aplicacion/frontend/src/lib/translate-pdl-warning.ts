import type { TranslateFn } from "@/i18n";
import type { TranslationKey } from "@/i18n/types";

const EXACT_LEGACY: Record<string, TranslationKey> = {
  "PDL encontró perfil (sin LinkedIn en respuesta).": "detail.warn_pdl_profile_no_linkedin",
  "No se encontró perfil verificable. Prueba email corporativo, LinkedIn o acrónimo de empresa.":
    "detail.warn_pdl_no_profile",
  "No se encontró información adicional sobre esta persona. Añade más información o revisa que el nombre completo sea correcto para mayor exactitud.":
    "detail.warn_pdl_no_profile",
  "PDL incluye email/teléfono en el match cuando existen; no hay paso «reveal» aparte.":
    "detail.warn_pdl_contact_in_match",
  "El email y teléfono se incluyen en el match cuando existen; no hay paso «reveal» aparte.":
    "detail.warn_pdl_contact_in_match",
};

/** Textos de `PDL_FAILURE_WARNINGS` (backend/src/dossier/services/pdl_research.py). */
const PDL_FAILURES: Record<string, TranslationKey> = {
  "No se pudo completar la consulta de registros de esta persona: el proveedor de datos rechazó el acceso. Avisa al administrador.":
    "detail.warn_pdl_auth",
  "No se pudo completar la consulta de registros de esta persona: el proveedor de datos no está configurado. Avisa al administrador.":
    "detail.warn_pdl_config",
  "No se pudo completar la consulta de registros de esta persona: se agotaron los créditos del proveedor de datos. Avisa al administrador.":
    "detail.warn_pdl_credits",
  "No se pudo completar la consulta de registros de esta persona: el proveedor de datos recibió demasiadas solicitudes. Espera un momento y vuelve a generar el dossier.":
    "detail.warn_pdl_rate_limit",
  "No se pudo completar la consulta de registros de esta persona: el proveedor de datos tardó demasiado en responder. Vuelve a intentarlo más tarde.":
    "detail.warn_pdl_timeout",
  "No se pudo completar la consulta de registros de esta persona: el proveedor de datos respondió con un error. Vuelve a intentarlo más tarde.":
    "detail.warn_pdl_error",
};

/** Avisos de falla guardados en dossiers anteriores. El orden importa: el genérico va al final. */
const PDL_FAILURES_LEGACY: [RegExp, TranslationKey][] = [
  [/^Falta PDL_API_KEY/i, "detail.warn_pdl_config"],
  [/^PDL (respondió|HTTP) (401|403)\b|^PDL \(auth/i, "detail.warn_pdl_auth"],
  [/^PDL (respondió|HTTP) 402\b|^PDL \(payment|^PDL: créditos/i, "detail.warn_pdl_credits"],
  [/^PDL (respondió|HTTP) 429\b|^PDL \(rate|^Límite de solicitudes alcanzado/i, "detail.warn_pdl_rate_limit"],
  [/^PDL (respondió|HTTP) (408|504)\b/i, "detail.warn_pdl_timeout"],
  [/^PDL (HTTP \d|\(|:)/i, "detail.warn_pdl_error"],
];

/** Clave del motivo si el aviso dice que el proveedor de datos falló; `null` si no es una falla. */
export function pdlFailureKey(warning: string): TranslationKey | null {
  const w = warning.trim();
  return PDL_FAILURES[w] ?? PDL_FAILURES_LEGACY.find(([re]) => re.test(w))?.[1] ?? null;
}

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

  const failure = pdlFailureKey(w);
  return failure ? t(failure) : w;
}
