/** Metadatos de reunión guardados en `dossier_data.calendar`. */
import type { TranslationKey, UserPreferences } from "@/i18n/types";
import { formatCalendarMeetingInstant } from "@/lib/format";

export type CalendarDossierMeta = {
  provider?: string;
  external_event_id?: string;
  tema?: string;
  inicio?: string;
  fin?: string;
  meeting_label?: string;
};

function readCalendarBlock(dossierData: unknown): CalendarDossierMeta | null {
  if (!dossierData || typeof dossierData !== "object" || Array.isArray(dossierData)) {
    return null;
  }
  const cal = (dossierData as Record<string, unknown>).calendar;
  if (!cal || typeof cal !== "object" || Array.isArray(cal)) return null;
  return cal as CalendarDossierMeta;
}

function stripMeetingDatetimeSuffix(label: string): string {
  const sep = " · ";
  const idx = label.lastIndexOf(sep);
  if (idx <= 0) return label;
  const tail = label.slice(idx + sep.length);
  if (/^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}(?:[,\s]+?\d{1,2}:\d{2})?/.test(tail)) {
    const subject = label.slice(0, idx).trim();
    return subject || label;
  }
  return label;
}

function buildMeetingLabelFromBlock(
  cal: CalendarDossierMeta,
  prefs?: Pick<UserPreferences, "locale" | "timezone">,
): string | null {
  const tema = cal.tema?.trim() || stripMeetingDatetimeSuffix(cal.meeting_label?.trim() || "");
  if (!tema) return null;
  if (prefs && cal.inicio?.trim()) {
    const when = formatCalendarMeetingInstant(cal.inicio, prefs);
    return when ? `${tema} · ${when}` : tema;
  }
  const explicit = cal.meeting_label?.trim();
  if (explicit) return explicit;
  return tema;
}

/** Etiqueta legible de la reunión de calendario asociada al dossier. */
export function getCalendarMeetingLabel(
  dossier: {
    trigger_source?: string | null;
    calendar_meeting?: string | null;
    dossier_data?: unknown;
  },
  prefs?: Pick<UserPreferences, "locale" | "timezone">,
): string | null {
  const source = (dossier.trigger_source || "").trim();
  const cal = readCalendarBlock(dossier.dossier_data);

  if (cal && prefs?.timezone) {
    const rebuilt = buildMeetingLabelFromBlock(cal, prefs);
    if (rebuilt) return rebuilt;
  }

  const fromApi = dossier.calendar_meeting?.trim();
  if (fromApi) return fromApi;

  if (!cal && source !== "calendar") return null;
  if (!cal) return null;

  return buildMeetingLabelFromBlock(cal);
}

/** Asunto de la reunión sin fecha/hora (para títulos grandes en tarjetas). */
export function getCalendarMeetingSubject(dossier: {
  calendar_meeting?: string | null;
  dossier_data?: unknown;
}): string | null {
  const cal = readCalendarBlock(dossier.dossier_data);
  const tema = cal?.tema?.trim();
  if (tema) return tema;

  const explicit = cal?.meeting_label?.trim();
  if (explicit) return stripMeetingDatetimeSuffix(explicit);

  const fromApi = dossier.calendar_meeting?.trim();
  if (fromApi) return stripMeetingDatetimeSuffix(fromApi);

  if (dossier.dossier_data && typeof dossier.dossier_data === "object" && !Array.isArray(dossier.dossier_data)) {
    const cf = (dossier.dossier_data as Record<string, unknown>).calendar_folder;
    if (cf && typeof cf === "object" && !Array.isArray(cf)) {
      const title = (cf as Record<string, unknown>).title;
      if (typeof title === "string" && title.trim()) {
        return stripMeetingDatetimeSuffix(title.trim());
      }
    }
  }

  return null;
}

export function isCalendarDossier(dossier: {
  trigger_source?: string | null;
  dossier_data?: unknown;
}): boolean {
  if ((dossier.trigger_source || "").trim() === "calendar") return true;
  return readCalendarBlock(dossier.dossier_data) !== null;
}

export function getCalendarProviderLabelKey(
  provider: string | undefined,
): TranslationKey | null {
  const p = (provider || "").trim().toLowerCase();
  if (p === "google") return "overview.google_title";
  if (p === "microsoft" || p === "outlook") return "overview.microsoft_title";
  return null;
}

/** @deprecated Usa `getCalendarProviderLabelKey` con el traductor `t()`. */
export function getCalendarProviderLabel(provider: string | undefined): string | null {
  const key = getCalendarProviderLabelKey(provider);
  if (key === "overview.google_title") return "Google Calendar";
  if (key === "overview.microsoft_title") return "Outlook";
  return provider?.trim() || null;
}

export { readCalendarBlock as readCalendarBlockFromData };
