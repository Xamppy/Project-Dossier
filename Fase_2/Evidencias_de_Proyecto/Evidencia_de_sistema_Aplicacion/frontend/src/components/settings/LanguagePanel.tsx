"use client";

import DashboardCard from "@/components/dashboard/DashboardCard";
import TimezoneSelect from "@/components/settings/TimezoneSelect";
import type { TranslationKey } from "@/i18n/types";
import { usePreferences } from "@/providers/PreferencesProvider";
import {
  DOSSIER_OUTPUT_LANGUAGE_CODES,
  SUPPORTED_LOCALES,
  type DateFormat,
  type DossierOutputLanguageCode,
  type Locale,
  type OutputLanguage,
} from "@/i18n/types";

const DATE_FORMAT_OPTIONS: { value: DateFormat; label: string }[] = [
  { value: "dd/mm/yyyy", label: "DD/MM/YYYY" },
  { value: "mm/dd/yyyy", label: "MM/DD/YYYY" },
  { value: "yyyy-mm-dd", label: "YYYY-MM-DD" },
];

const LOCALE_OPTION_KEYS: Record<Locale, TranslationKey> = {
  en: "locale.en",
  "en-gb": "locale.en_gb",
  es: "locale.es",
  pt: "locale.pt",
  it: "locale.it",
  fr: "locale.fr",
  de: "locale.de",
};

const OUTPUT_LANGUAGE_KEYS: Record<DossierOutputLanguageCode, TranslationKey> = {
  es: "locale.es",
  en: "locale.en",
  pt: "locale.pt",
  it: "locale.it",
  fr: "locale.fr",
  de: "locale.de",
};

export default function LanguagePanel() {
  const {
    t,
    preferences,
    setLocale,
    setDateFormat,
    setOutputLanguage,
    updatePreferences,
  } = usePreferences();

  return (
    <DashboardCard title={t("settings.language_title")}>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-sm">
          <span style={{ color: "var(--text-secondary)" }}>
            {t("settings.display_language")}
          </span>
          <select
            value={preferences.locale}
            onChange={(e) => setLocale(e.target.value as Locale)}
            className="ui-settings-select"
          >
            {SUPPORTED_LOCALES.map((loc) => (
              <option key={loc} value={loc}>
                {t(LOCALE_OPTION_KEYS[loc])}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5 text-sm">
          <span style={{ color: "var(--text-secondary)" }}>
            {t("settings.timezone")}
          </span>
          <TimezoneSelect
            timezone={preferences.timezone}
            followSystem={preferences.timezoneFollowSystem ?? false}
            onChange={({ timezone, followSystem }) =>
              updatePreferences({ timezone, timezoneFollowSystem: followSystem })
            }
            locale={preferences.locale}
            systemLabel={t("settings.timezone_system")}
            t={t}
            className="ui-settings-select"
          />
        </label>

        <label className="flex flex-col gap-1.5 text-sm">
          <span style={{ color: "var(--text-secondary)" }}>
            {t("settings.date_format")}
          </span>
          <select
            value={preferences.dateFormat}
            onChange={(e) => setDateFormat(e.target.value as DateFormat)}
            className="ui-settings-select"
          >
            {DATE_FORMAT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5 text-sm">
          <span style={{ color: "var(--text-secondary)" }}>
            {t("settings.output_language")}
          </span>
          <select
            value={preferences.outputLanguage}
            onChange={(e) => setOutputLanguage(e.target.value as OutputLanguage)}
            className="ui-settings-select"
          >
            <option value="match">{t("output.match")}</option>
            {DOSSIER_OUTPUT_LANGUAGE_CODES.map((code) => (
              <option key={code} value={code}>
                {t(OUTPUT_LANGUAGE_KEYS[code])}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="mt-4 text-xs" style={{ color: "var(--text-subtle)" }}>
        {t("settings.output_hint")}
      </p>
    </DashboardCard>
  );
}
