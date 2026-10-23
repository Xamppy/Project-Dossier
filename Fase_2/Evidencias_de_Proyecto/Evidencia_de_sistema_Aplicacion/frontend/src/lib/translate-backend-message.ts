/**
 * Traduce textos emitidos por el backend (español fijo) al locale de la UI.
 * Los mensajes técnicos o no mapeados se registran en consola y no se muestran al cliente.
 */
import type { TranslateFn } from "@/i18n";
import type { TranslationKey } from "@/i18n/types";
import type { DossierApiError } from "@/lib/dossier-api";
import {
  finalizeBackendUserMessage,
  isTechnicalBackendMessage,
  toPublicErrorMessage,
} from "@/lib/public-error-message";
import { translatePdlWarning } from "@/lib/translate-pdl-warning";

import { translateApiError } from "@/lib/translate-api-error";

const EXACT_STATUS: Record<string, TranslationKey> = {
  "Error en el informe generado.": "backend.status_report_error",
  "Error en síntesis o en el pipeline.": "backend.status_pipeline_error",
  "Error al generar el análisis de persona.": "backend.status_person_analysis_error",
  "Cancelado por el usuario": "backend.status_cancelled_by_user",
  "No se pudo generar el análisis de persona. Reintenta la generación o usa «Nueva búsqueda de persona» con más datos.":
    "backend.status_person_retry_hint",
};

const EXACT_API_MESSAGE: Record<string, TranslationKey> = {
  "Ya existe una cuenta con este email. Prueba a iniciar sesión.":
    "backend.error_email_exists",
  "Ya existe una cuenta con este email.":
    "backend.error_email_in_use",
  "Contraseña incorrecta.": "backend.error_wrong_password",
  "No puedes eliminar tu propia cuenta desde el panel de administración.":
    "backend.error_admin_delete_self",
  "La invitación ya no es válida.": "backend.error_invite_invalid",
  "Debes registrarte con el correo al que se envió la invitación.":
    "backend.error_invite_email_mismatch",
  "No hay sesión. Inicia sesión de nuevo.": "backend.error_no_session",
  "Créditos insuficientes: se requieren {cost} y la organización tiene {balance}.":
    "backend.error_insufficient_credits",
  "Job no encontrado.": "backend.error_job_not_found",
  "Locale no soportado.": "backend.error_locale_unsupported",
};

const PREFIX_API: { prefix: string; key: TranslationKey }[] = [
  { prefix: "Créditos insuficientes:", key: "backend.error_insufficient_credits_generic" },
  { prefix: "Los dossiers de empresa requieren plan", key: "billing.corporate_requires_pro" },
  { prefix: "La automatización de calendario requiere plan", key: "billing.automation_requires_pro" },
  { prefix: "Tu plan ", key: "backend.error_plan_depth" },
  {
    prefix: "Eres el único administrador de una organización",
    key: "backend.error_account_sole_admin",
  },
  {
    prefix: "No puedes eliminar una cuenta con rol de administrador de plataforma",
    key: "backend.error_account_platform_admin",
  },
];

function translateKnownStatus(raw: string, t: TranslateFn): string {
  const msg = raw.trim();
  const exact = EXACT_STATUS[msg];
  if (exact) return t(exact);
  const pdl = translatePdlWarning(msg, t);
  if (pdl !== msg) return pdl;
  return msg;
}

export function translateDossierStatusMessage(
  raw: string | null | undefined,
  t: TranslateFn,
): string | null {
  if (!raw?.trim()) return null;
  const msg = raw.trim();
  const translated = translateKnownStatus(msg, t);
  return finalizeBackendUserMessage(msg, translated, t, "status");
}

/** Avisos PDL/DeepSeek y otros warnings del pipeline de persona. */
export function translateBackendWarning(warning: string, t: TranslateFn): string {
  const w = warning.trim();
  if (!w) return w;

  const pdl = translatePdlWarning(w, t);
  if (pdl !== w) return pdl;

  const exact = EXACT_STATUS[w];
  if (exact) return t(exact);

  if (isTechnicalBackendMessage(w)) {
    console.error("[SistemaDossier:warning]", w);
    return "";
  }

  console.warn("[SistemaDossier:warning:unmapped]", w);
  return "";
}

export function translateApiErrorMessage(
  err: DossierApiError | string,
  t: TranslateFn,
): string {
  if (typeof err === "string") {
    return translateLegacyApiMessage(err, t);
  }
  const translated = translateApiError(err, t);
  if (translated !== err.message) return translated;
  return translateLegacyApiMessage(err.message, t);
}

function translateLegacyApiMessage(message: string, t: TranslateFn): string {
  const msg = message.trim();
  if (!msg) return t("errors.server_generic");

  const exact = EXACT_API_MESSAGE[msg];
  if (exact) return t(exact);

  for (const { prefix, key } of PREFIX_API) {
    if (msg.startsWith(prefix)) return t(key);
  }

  const creditsMatch = msg.match(
    /^Créditos insuficientes: se requieren (\d+) y la organización tiene (\d+)\.$/,
  );
  if (creditsMatch) {
    return t("backend.error_insufficient_credits", {
      cost: creditsMatch[1],
      balance: creditsMatch[2],
    });
  }

  return toPublicErrorMessage(msg, t, "api");
}

export { translateApiError };
