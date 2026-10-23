"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import PrimaryButton from "@/components/PrimaryButton";
import {
  disconnectCalendarIntegration,
  DossierApiError,
  fetchCalendarAutomationStatus,
  fetchGoogleIntegrationStartAsJson,
  fetchMicrosoftIntegrationStartAsJson,
  getStoredAccessToken,
  type CalendarProvider,
} from "@/lib/dossier-api";
import UiAlert from "@/components/ui/UiAlert";
import { translateApiErrorMessage } from "@/lib/translate-backend-message";
import { useTranslation } from "@/providers/PreferencesProvider";
import type { TranslationKey } from "@/i18n/types";

type Props = {
  provider: CalendarProvider;
  embedded?: boolean;
};

const I18N: Record<
  CalendarProvider,
  {
    connect: TranslationKey;
    connected: TranslationKey;
    loading: TranslationKey;
    error: TranslationKey;
    noConnection: TranslationKey;
    connectedHint: TranslationKey;
  }
> = {
  google: {
    connect: "overview.google_connect",
    connected: "overview.google_connected",
    loading: "overview.google_loading",
    error: "overview.google_error",
    noConnection: "overview.google_no_connection",
    connectedHint: "overview.google_connected_hint",
  },
  microsoft: {
    connect: "overview.microsoft_connect",
    connected: "overview.microsoft_connected",
    loading: "overview.microsoft_loading",
    error: "overview.microsoft_error",
    noConnection: "overview.microsoft_no_connection",
    connectedHint: "overview.microsoft_connected_hint",
  },
};

function maskEmail(email: string): string {
  const at = email.indexOf("@");
  if (at <= 0) return "••••••••";
  const local = email.slice(0, at);
  const domain = email.slice(at);
  if (local.length <= 1) return `•${domain}`;
  const hidden = "•".repeat(Math.min(Math.max(local.length - 1, 4), 10));
  return `${local[0]}${hidden}${domain}`;
}

function EyeIcon({ open }: { open: boolean }) {
  if (open) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden>
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden>
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}

export default function CalendarIntegrationPanel({ provider, embedded = false }: Props) {
  const { t } = useTranslation();
  const keys = I18N[provider];

  const [load, setLoad] = useState<"idle" | "loading" | "ready">("idle");
  const [connected, setConnected] = useState(false);
  const [accountEmail, setAccountEmail] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [emailVisible, setEmailVisible] = useState(false);

  const checkConnection = useCallback(async () => {
    if (!getStoredAccessToken()) {
      setErr(null);
      setConnected(false);
      setAccountEmail(null);
      setLoad("idle");
      return;
    }
    setLoad("loading");
    setErr(null);
    try {
      const status = await fetchCalendarAutomationStatus();
      const row = status.integrations?.find((i) => i.provider === provider);
      if (row) {
        setConnected(true);
        setAccountEmail(row.email?.trim() || null);
        setEmailVisible(false);
      } else {
        setConnected(false);
        setAccountEmail(null);
        setErr(t(keys.noConnection));
      }
      setLoad("ready");
    } catch (e) {
      setConnected(false);
      setAccountEmail(null);
      if (e instanceof DossierApiError && (e.status === 404 || e.status === 401)) {
        setErr(t(keys.noConnection));
      } else if (e instanceof DossierApiError && e.status === 0) {
        // Fallo de red / API caída: mensaje neutro de reintento, sin overlay de error.
        setErr(t("overview.calendar_network_retry"));
      } else if (e instanceof DossierApiError) {
        setErr(translateApiErrorMessage(e, t) || t(keys.error));
      } else {
        setErr(t(keys.error));
      }
      setLoad("ready");
    }
  }, [t, keys, provider]);

  useEffect(() => {
    queueMicrotask(() => {
      void checkConnection();
    });
  }, [checkConnection]);

  async function onConnect() {
    setConnecting(true);
    setErr(null);
    try {
      const { authorize_url } =
        provider === "google"
          ? await fetchGoogleIntegrationStartAsJson()
          : await fetchMicrosoftIntegrationStartAsJson();
      window.location.href = authorize_url;
    } catch (e) {
      setConnecting(false);
      if (e instanceof DossierApiError) setErr(e.message);
      else setErr(t(keys.error));
    }
  }

  async function onDisconnect() {
    setDisconnecting(true);
    setErr(null);
    try {
      await disconnectCalendarIntegration(provider);
      setConnected(false);
      setAccountEmail(null);
      setLoad("ready");
      setErr(t(keys.noConnection));
    } catch (e) {
      if (e instanceof DossierApiError) {
        const msg = e.message === "Not Found"
          ? t("overview.calendar_disconnect_server")
          : e.message;
        setErr(msg);
      } else {
        setErr(t(keys.error));
      }
    } finally {
      setDisconnecting(false);
    }
  }

  const token = typeof window !== "undefined" ? getStoredAccessToken() : null;
  const providerAccent = provider === "google" ? "#4285f4" : "#0078d4";
  const providerAccentBorder =
    provider === "google" ? "rgba(66,133,244,0.45)" : "rgba(0,120,212,0.45)";

  return (
    <div className={embedded ? "flex flex-col gap-3" : "flex flex-col gap-4 px-1 py-1"}>
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        {connected ? (
          <>
            <div
              className={`flex min-w-0 flex-col gap-1 rounded-lg border px-3 py-2.5 ${
                embedded ? "w-full sm:flex-1" : "w-full sm:min-w-[200px]"
              }`}
              style={{
                borderColor: providerAccentBorder,
                backgroundColor: "var(--bg-surface)",
              }}
            >
              <span
                className="inline-flex items-center gap-2 text-xs font-semibold sm:text-sm"
                style={{ color: providerAccent }}
              >
                <span aria-hidden className="text-base leading-none">
                  ✓
                </span>
                {t(keys.connected)}
              </span>
              {accountEmail ? (
                <div className="flex min-w-0 items-center gap-1">
                  <span
                    className="min-w-0 flex-1 truncate text-xs font-medium sm:text-sm"
                    style={{ color: "var(--text-primary)" }}
                    title={emailVisible ? accountEmail : undefined}
                  >
                    {emailVisible ? accountEmail : maskEmail(accountEmail)}
                  </span>
                  <button
                    type="button"
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition hover:bg-[var(--hover-overlay)]"
                    style={{ color: "var(--text-muted)" }}
                    aria-label={
                      emailVisible
                        ? t("overview.calendar_email_hide")
                        : t("overview.calendar_email_show")
                    }
                    aria-pressed={emailVisible}
                    onClick={() => setEmailVisible((v) => !v)}
                  >
                    <EyeIcon open={emailVisible} />
                  </button>
                </div>
              ) : (
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {t("overview.calendar_connected_no_email")}
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={() => void onDisconnect()}
              disabled={disconnecting}
              className={`ui-calendar-disconnect-btn gap-2 px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-60 sm:text-sm ${
                embedded ? "w-full sm:w-auto" : "w-full sm:w-auto"
              }`}
            >
              {disconnecting ? t("overview.calendar_disconnecting") : t("overview.calendar_disconnect")}
            </button>
          </>
        ) : (
          <PrimaryButton
            type="button"
            className={`ui-calendar-connect-btn ${embedded ? "w-full sm:flex-1" : "w-full sm:w-auto sm:min-w-[200px]"}`}
            loading={connecting}
            disabled={!token || load === "loading"}
            onClick={() => void onConnect()}
          >
            {t(keys.connect)}
          </PrimaryButton>
        )}
      </div>

      {err && !connected ? (
        <UiAlert variant="warning" role="alert">
          {err}
        </UiAlert>
      ) : null}

      {!token ? (
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {t("overview.activity_login_hint")}
        </p>
      ) : connected && load === "ready" ? (
        <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
          {t(keys.connectedHint)}{" "}
          <Link
            href="/dashboard/dossiers"
            className="font-medium underline-offset-2 hover:underline"
            style={{ color: "var(--accent-from)" }}
          >
            {t("nav.dossiers")}
          </Link>
          .
        </p>
      ) : null}
    </div>
  );
}
