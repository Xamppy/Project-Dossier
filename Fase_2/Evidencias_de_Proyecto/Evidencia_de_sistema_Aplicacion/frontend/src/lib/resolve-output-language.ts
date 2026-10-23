import type {
  DossierOutputLanguageCode,
  Locale,
  OutputLanguage,
  UserPreferences,
} from "@/i18n/types";
import { DOSSIER_OUTPUT_LANGUAGE_CODES } from "@/i18n/types";

export type { DossierOutputLanguageCode };

function localeToOutputCode(locale: Locale): DossierOutputLanguageCode {
  switch (locale) {
    case "en":
    case "en-gb":
      return "en";
    case "pt":
      return "pt";
    case "it":
      return "it";
    case "fr":
      return "fr";
    case "de":
      return "de";
    default:
      return "es";
  }
}

function isExplicitOutputCode(value: OutputLanguage): value is DossierOutputLanguageCode {
  return (DOSSIER_OUTPUT_LANGUAGE_CODES as readonly string[]).includes(value);
}

/**
 * Resuelve el idioma de salida según Configuración → Idioma y Región.
 *
 * - `match`: mismo idioma que la interfaz (`locale`).
 * - `es` | `en` | `pt` | `it` | `fr` | `de`: idioma fijo del dossier.
 * - `auto`: español (legado).
 */
export function resolveDossierOutputLanguage(
  prefs: Pick<UserPreferences, "locale" | "outputLanguage">
): DossierOutputLanguageCode {
  if (prefs.outputLanguage === "match") {
    return localeToOutputCode(prefs.locale);
  }
  if (isExplicitOutputCode(prefs.outputLanguage)) {
    return prefs.outputLanguage;
  }
  return "es";
}
