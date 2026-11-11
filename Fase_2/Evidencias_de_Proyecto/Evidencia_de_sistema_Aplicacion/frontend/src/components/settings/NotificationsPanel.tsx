"use client";

import { useEffect, useState } from "react";
import DashboardCard from "@/components/dashboard/DashboardCard";
import Toggle from "@/components/ui/Toggle";
import { useTranslation } from "@/providers/PreferencesProvider";
import type { TranslationKey } from "@/i18n/types";
import { fetchAuthMe, getStoredAccessToken, patchAuthUserPreferences } from "@/lib/dossier-api";
import {
  browserNotificationsSupported,
  requestBrowserNotifyPermission,
  setBrowserNotifyPref,
} from "@/lib/browser-notifications";

/**
 * Preferencias de notificación (informe beta del 2026-10-06: no se guardaban).
 *
 * Correo y navegador se guardan en la cuenta y se respetan: sin correo no se envía el PDF
 * automático (el botón «Enviar por correo» sigue funcionando); con navegador, el sistema operativo
 * avisa cuando llega un dossier nuevo. Alertas de riesgo y resumen semanal no existen todavía.
 */

type Guardable = "email" | "browser";

const GUARDABLES: { key: Guardable; labelKey: TranslationKey; descKey: TranslationKey }[] = [
  { key: "email", labelKey: "notif.email_label", descKey: "notif.email_desc" },
  { key: "browser", labelKey: "notif.browser_label", descKey: "notif.browser_desc" },
];

const PROXIMAMENTE: { key: string; labelKey: TranslationKey; descKey: TranslationKey }[] = [
  { key: "risk", labelKey: "notif.risk_label", descKey: "notif.risk_desc" },
  { key: "weekly", labelKey: "notif.weekly_label", descKey: "notif.weekly_desc" },
];

type Aviso = { kind: "error" | "info"; key: TranslationKey } | null;

function Fila({
  label,
  desc,
  extra,
  children,
}: {
  label: string;
  desc: string;
  extra?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <li
      className="flex items-center justify-between gap-4 rounded-lg border px-4 py-3"
      style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-surface)" }}
    >
      <div className="flex flex-col">
        <span className="flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-primary)" }}>
          {label}
          {extra}
        </span>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          {desc}
        </span>
      </div>
      {children}
    </li>
  );
}

export default function NotificationsPanel() {
  const { t } = useTranslation();
  const [prefs, setPrefs] = useState<Record<Guardable, boolean> | null>(null);
  const [guardando, setGuardando] = useState<Guardable | null>(null);
  const [aviso, setAviso] = useState<Aviso>(null);

  useEffect(() => {
    if (!getStoredAccessToken()) return;
    let cancelled = false;
    void fetchAuthMe()
      .then((me) => {
        if (cancelled) return;
        const browser = me.notify_browser !== false;
        setPrefs({ email: me.notify_email !== false, browser });
        setBrowserNotifyPref(browser);
      })
      .catch(() => {
        if (!cancelled) setAviso({ kind: "error", key: "notif.load_error" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function cambiar(key: Guardable, value: boolean) {
    if (!prefs) return;
    setAviso(null);
    if (key === "browser" && value) {
      if (!browserNotificationsSupported()) {
        setAviso({ kind: "error", key: "notif.browser_unsupported" });
        return;
      }
      if (!(await requestBrowserNotifyPermission())) {
        setAviso({ kind: "error", key: "notif.browser_blocked" });
        return;
      }
    }
    const anterior = prefs;
    setPrefs({ ...prefs, [key]: value });
    setGuardando(key);
    try {
      const me = await patchAuthUserPreferences(key === "email" ? { notify_email: value } : { notify_browser: value });
      setPrefs({ email: me.notify_email !== false, browser: me.notify_browser !== false });
      if (key === "browser") setBrowserNotifyPref(me.notify_browser !== false);
    } catch {
      setPrefs(anterior);
      setAviso({ kind: "error", key: "notif.save_error" });
    } finally {
      setGuardando(null);
    }
  }

  return (
    <DashboardCard title={t("settings.notifications_title")}>
      <ul className="flex flex-col gap-3">
        {GUARDABLES.map((item) => (
          <Fila key={item.key} label={t(item.labelKey)} desc={t(item.descKey)}>
            <Toggle
              checked={prefs?.[item.key] ?? false}
              disabled={prefs === null || guardando !== null}
              onChange={(v) => void cambiar(item.key, v)}
            />
          </Fila>
        ))}
        {PROXIMAMENTE.map((item) => (
          <Fila
            key={item.key}
            label={t(item.labelKey)}
            desc={t(item.descKey)}
            extra={
              <span
                className="rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide"
                style={{ borderColor: "var(--border-default)", color: "var(--text-muted)" }}
              >
                {t("notif.coming_soon")}
              </span>
            }
          >
            <Toggle checked={false} disabled onChange={() => {}} />
          </Fila>
        ))}
      </ul>
      {aviso ? (
        <p
          role={aviso.kind === "error" ? "alert" : "status"}
          className="mt-3 text-sm"
          style={{ color: aviso.kind === "error" ? "var(--accent-danger, #f87171)" : "var(--text-secondary)" }}
        >
          {t(aviso.key)}
        </p>
      ) : null}
    </DashboardCard>
  );
}
