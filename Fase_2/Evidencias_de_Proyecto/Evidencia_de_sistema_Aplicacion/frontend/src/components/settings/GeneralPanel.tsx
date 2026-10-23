"use client";

import DashboardCard from "@/components/dashboard/DashboardCard";
import ThemePreview from "@/components/settings/ThemePreview";
import { usePreferences } from "@/providers/PreferencesProvider";
import type { ThemeChoice, TranslationKey } from "@/i18n/types";

const THEME_OPTIONS: { id: ThemeChoice; labelKey: TranslationKey }[] = [
  { id: "dark", labelKey: "theme.dark" },
  { id: "light", labelKey: "theme.light" },
  { id: "system", labelKey: "theme.system" },
];

const EXPIRY_OPTIONS: { value: string; labelKey: TranslationKey }[] = [
  { value: "7", labelKey: "expiry.7" },
  { value: "14", labelKey: "expiry.14" },
  { value: "30", labelKey: "expiry.30" },
  { value: "90", labelKey: "expiry.90" },
  { value: "never", labelKey: "expiry.never" },
];

const selectClass =
  "w-full rounded-lg border px-3.5 py-2.5 text-sm outline-none focus:ring-2";

const selectStyle = {
  backgroundColor: "var(--bg-input)",
  borderColor: "var(--border-default)",
  color: "var(--text-primary)",
};

export default function GeneralPanel() {
  const { t, preferences, setTheme, setDossierExpiry } = usePreferences();

  return (
    <DashboardCard title={t("settings.general_title")}>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
            {t("settings.theme")}
          </span>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {THEME_OPTIONS.map(({ id, labelKey }) => {
              const isActive = preferences.theme === id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setTheme(id)}
                  aria-pressed={isActive}
                  className={
                    isActive
                      ? "ui-theme-picker-btn ui-theme-picker-btn--active"
                      : "ui-theme-picker-btn ui-theme-picker-btn--inactive"
                  }
                >
                  <div className="w-full max-w-[120px]">
                    <ThemePreview variant={id} />
                  </div>
                  <span className="text-sm font-medium">{t(labelKey)}</span>
                </button>
              );
            })}
          </div>
        </div>

        <label className="flex flex-col gap-1.5 text-sm">
          <span style={{ color: "var(--text-secondary)" }}>
            {t("settings.expiry")}
          </span>
          <select
            value={preferences.dossierExpiry}
            onChange={(e) => setDossierExpiry(e.target.value)}
            className={selectClass}
            style={selectStyle}
          >
            {EXPIRY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(opt.labelKey)}
              </option>
            ))}
          </select>
          <span className="text-xs" style={{ color: "var(--text-subtle)" }}>
            {t("settings.expiry_hint")}
          </span>
        </label>
      </div>
    </DashboardCard>
  );
}
