import type { AuthUser } from "@/lib/dossier-api";
import type { OutputLanguage, UserPreferences } from "@/i18n/types";
import { normalizeAppLocale } from "@/i18n/types";
import { getEffectiveTimezone } from "@/lib/timezones";

const OUTPUT_LANGUAGE_PREFS: OutputLanguage[] = [
  "match",
  "auto",
  "es",
  "en",
  "pt",
  "it",
  "fr",
  "de",
];

function isOutputLanguagePref(value: string): value is OutputLanguage {
  return (OUTPUT_LANGUAGE_PREFS as readonly string[]).includes(value);
}

/** Campos de preferencias que vienen del backend (`GET /auth/me`). */
export function authUserToPreferencesPatch(me: AuthUser): Partial<UserPreferences> {
  const patch: Partial<UserPreferences> = {};
  const loc = normalizeAppLocale(me.locale);
  if (loc) {
    patch.locale = loc;
  }
  const tz = (me.timezone || "").trim();
  if (tz) {
    patch.timezone = tz;
    patch.timezoneFollowSystem = false;
  }
  const out = (me.dossier_output_language || "").trim();
  if (out && isOutputLanguagePref(out)) {
    patch.outputLanguage = out;
  }
  // S6.5: el plazo lo fija el servidor; aquí solo se muestra.
  const horas = me.dossier_retention_hours;
  if (typeof horas === "number" && horas > 0) {
    patch.dossierRetentionHours = horas;
  }
  return patch;
}

/** Lo que el dashboard envía a `PATCH /auth/me/preferences`. La retención ya no viaja (S6.5). */
export function preferencesToAuthPatch(
  prefs: Pick<UserPreferences, "locale" | "timezone" | "timezoneFollowSystem" | "outputLanguage">
): {
  locale: string;
  timezone: string;
  dossier_output_language: string;
} {
  return {
    locale: normalizeAppLocale(prefs.locale),
    timezone: getEffectiveTimezone(prefs.timezone, prefs.timezoneFollowSystem ?? false),
    dossier_output_language: prefs.outputLanguage,
  };
}
