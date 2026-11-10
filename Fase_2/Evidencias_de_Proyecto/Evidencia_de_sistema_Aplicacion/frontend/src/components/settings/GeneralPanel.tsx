"use client";

import DashboardCard from "@/components/dashboard/DashboardCard";
import ThemePreview from "@/components/settings/ThemePreview";
import { usePreferences } from "@/providers/PreferencesProvider";
import { DEFAULT_PREFERENCES, type ThemeChoice, type TranslationKey } from "@/i18n/types";

const THEME_OPTIONS: { id: ThemeChoice; labelKey: TranslationKey }[] = [
  { id: "dark", labelKey: "theme.dark" },
  { id: "light", labelKey: "theme.light" },
  { id: "system", labelKey: "theme.system" },
];

export default function GeneralPanel() {
  const { t, preferences, setTheme } = usePreferences();

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

        {/* S6.5: la retención la fija el servidor para todos; aquí solo se informa. */}
        <div className="flex flex-col gap-1.5 text-sm">
          <span style={{ color: "var(--text-secondary)" }}>{t("settings.expiry")}</span>
          <p style={{ color: "var(--text-primary)" }}>
            {t("settings.expiry_fixed", {
              hours: preferences.dossierRetentionHours ?? DEFAULT_PREFERENCES.dossierRetentionHours,
            })}
          </p>
        </div>
      </div>
    </DashboardCard>
  );
}
