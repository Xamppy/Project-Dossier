"use client";

import { useState } from "react";
import type { TranslationKey } from "@/i18n/types";
import {
  DossierApiError,
  sendDossierByEmail,
  type DossierEmailDelivery,
} from "@/lib/dossier-api";
import { formatLongDate } from "@/lib/format";
import { translateApiErrorMessage } from "@/lib/translate-backend-message";
import { useTranslation } from "@/providers/PreferencesProvider";

type Props = {
  dossierId: string;
  /** La instancia tiene SMTP configurado (`/auth/me`). */
  available: boolean;
  /** Solo un dossier completo se puede enviar. */
  complete: boolean;
  userEmail: string | null | undefined;
  initialDelivery?: DossierEmailDelivery | null;
};

// Errores de POST /dossiers/{id}/email por estado: no dependen del texto del backend.
const ERRORES_POR_ESTADO: Record<number, TranslationKey> = {
  409: "dossiers.email_error_not_complete",
  429: "dossiers.email_error_too_soon",
  502: "dossiers.email_error_failed",
  503: "dossiers.email_error_unavailable",
};

/** S6.1: envía el dossier completo al correo del propio usuario. */
export default function EmailDossierPanel({
  dossierId,
  available,
  complete,
  userEmail,
  initialDelivery,
}: Props) {
  const { t, preferences } = useTranslation();
  const [delivery, setDelivery] = useState<DossierEmailDelivery>(
    initialDelivery ?? { sent: false, sent_at: null, recipients: [] },
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);

  if (!available || !complete || !userEmail) return null;

  async function handleSend() {
    if (busy) return;
    setBusy(true);
    setError(null);
    setSentTo(null);
    try {
      const res = await sendDossierByEmail(dossierId);
      setDelivery({ sent: res.email_sent, sent_at: res.email_sent_at, recipients: res.email_recipients });
      setSentTo(userEmail ?? null);
    } catch (e) {
      const key = e instanceof DossierApiError ? ERRORES_POR_ESTADO[e.status] : undefined;
      setError(
        key
          ? t(key)
          : e instanceof DossierApiError
            ? translateApiErrorMessage(e, t)
            : t("dossiers.email_error_failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="rounded-xl border px-4 py-4"
      style={{
        borderColor: "var(--border-default)",
        backgroundColor: "var(--bg-surface)",
      }}
    >
      <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
        {t("dossiers.email_title")}
      </h3>
      <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
        {t("dossiers.email_hint", { email: userEmail })}
      </p>

      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs" style={{ color: "var(--text-subtle)" }}>
          {delivery.sent && delivery.sent_at
            ? t("dossiers.email_last_sent", {
                date: formatLongDate(delivery.sent_at, preferences),
                recipients: delivery.recipients.join(", "),
              })
            : t("dossiers.email_never_sent")}
        </p>
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleSend()}
          className="rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          style={{
            backgroundImage:
              "linear-gradient(135deg, var(--accent-from) 0%, var(--accent-to) 100%)",
          }}
        >
          {busy ? t("dossiers.email_sending") : t("dossiers.email_button")}
        </button>
      </div>

      {sentTo ? (
        <p className="mt-3 text-xs" style={{ color: "var(--status-success)" }} role="status">
          {t("dossiers.email_sent_ok", { email: sentTo })}
        </p>
      ) : null}
      {error ? (
        <p className="mt-3 text-xs text-red-400" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
