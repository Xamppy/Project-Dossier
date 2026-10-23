import type { TranslateFn } from "@/i18n";
import type { TranslationKey } from "@/i18n/types";

/** Patrones que no deben mostrarse al usuario final (config, claves, infra). */
const TECHNICAL_PATTERNS: RegExp[] = [
  /\.env\b/i,
  /API_KEY/i,
  /API Keys/i,
  /People Data Labs/i,
  /DEEPSEEK/i,
  /GEMINI/i,
  /PDL_API/i,
  /LUSHA/i,
  /JWT_SECRET/i,
  /DATABASE_URL/i,
  /Migracion\.md/i,
  /patch_after_migracion/i,
  /Falta .+ en el entorno/i,
  /Sin perfiles de PDL/i,
  /no se pudo ejecutar el análisis con IA/i,
  /traceback/i,
  /sqlalchemy/i,
  /postgresql/i,
  /internal server error/i,
];

export type PublicErrorContext = "api" | "status" | "warning";

export function isTechnicalBackendMessage(message: string): boolean {
  const m = message.trim();
  if (!m) return false;
  return TECHNICAL_PATTERNS.some((re) => re.test(m));
}

function fallbackKey(context: PublicErrorContext): TranslationKey {
  switch (context) {
    case "status":
      return "errors.generation_failed";
    case "warning":
      return "errors.service_unavailable";
    default:
      return "errors.server_generic";
  }
}

/** Mensajes benignos (red, sin sesión) que no merecen registro. */
const BENIGN_MESSAGES = new Set(["NETWORK", "Not Found", ""]);

/**
 * Registra el mensaje real en consola (como warn, para no disparar el overlay de
 * error de Next en desarrollo) y devuelve un texto genérico traducido para la UI.
 */
export function toPublicErrorMessage(
  raw: string | null | undefined,
  t: TranslateFn,
  context: PublicErrorContext = "api",
): string {
  const msg = raw?.trim() ?? "";
  if (!msg) return t(fallbackKey(context));

  if (!BENIGN_MESSAGES.has(msg)) {
    // console.warn no dispara el overlay rojo de Next.js dev; sigue visible en la consola.
    console.warn(`[SistemaDossier:${context}]`, msg);
  }

  return t(fallbackKey(context));
}

/**
 * Si el mensaje ya está traducido (mapeo conocido), lo devuelve.
 * Si no, lo sanitiza para el cliente.
 */
export function finalizeBackendUserMessage(
  raw: string,
  translated: string,
  t: TranslateFn,
  context: PublicErrorContext,
): string {
  const msg = raw.trim();
  if (!msg) return "";

  if (translated !== msg && !isTechnicalBackendMessage(translated)) {
    return translated;
  }

  if (isTechnicalBackendMessage(msg) || translated === msg) {
    return toPublicErrorMessage(msg, t, context);
  }

  return translated;
}
