"use client";

import { useState } from "react";
import DashboardCard from "@/components/dashboard/DashboardCard";
import Toggle from "@/components/ui/Toggle";
import { useTranslation } from "@/providers/PreferencesProvider";
import type { TranslationKey } from "@/i18n/types";

type NotificationKey = "email" | "browser" | "risk" | "weekly";

const NOTIFICATIONS: {
  key: NotificationKey;
  labelKey: TranslationKey;
  descKey: TranslationKey;
  defaultOn: boolean;
}[] = [
  {
    key: "email",
    labelKey: "notif.email_label",
    descKey: "notif.email_desc",
    defaultOn: true,
  },
  {
    key: "browser",
    labelKey: "notif.browser_label",
    descKey: "notif.browser_desc",
    defaultOn: true,
  },
  {
    key: "risk",
    labelKey: "notif.risk_label",
    descKey: "notif.risk_desc",
    defaultOn: true,
  },
  {
    key: "weekly",
    labelKey: "notif.weekly_label",
    descKey: "notif.weekly_desc",
    defaultOn: false,
  },
];

export default function NotificationsPanel() {
  const { t } = useTranslation();
  const [prefs, setPrefs] = useState<Record<NotificationKey, boolean>>(() =>
    Object.fromEntries(
      NOTIFICATIONS.map((n) => [n.key, n.defaultOn])
    ) as Record<NotificationKey, boolean>
  );

  function toggle(key: NotificationKey, value: boolean) {
    setPrefs((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <DashboardCard title={t("settings.notifications_title")}>
      <ul className="flex flex-col gap-3">
        {NOTIFICATIONS.map((item) => (
          <li
            key={item.key}
            className="flex items-center justify-between gap-4 rounded-lg border px-4 py-3"
            style={{
              borderColor: "var(--border-default)",
              backgroundColor: "var(--bg-surface)",
            }}
          >
            <div className="flex flex-col">
              <span
                className="text-sm font-medium"
                style={{ color: "var(--text-primary)" }}
              >
                {t(item.labelKey)}
              </span>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                {t(item.descKey)}
              </span>
            </div>
            <Toggle
              checked={prefs[item.key]}
              onChange={(v) => toggle(item.key, v)}
            />
          </li>
        ))}
      </ul>
    </DashboardCard>
  );
}
