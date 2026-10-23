import type { Locale, UserPreferences } from "@/i18n/types";

const LOCALE_MAP: Record<Locale, string> = {
  en: "en-US",
  "en-gb": "en-GB",
  es: "es-ES",
  pt: "pt-PT",
  it: "it-IT",
  fr: "fr-FR",
  de: "de-DE",
};

function intlLocale(locale: Locale): string {
  return LOCALE_MAP[locale] ?? "en-US";
}

export function formatDate(
  date: Date | string,
  prefs: Pick<UserPreferences, "locale" | "timezone" | "dateFormat">
): string {
  const d = typeof date === "string" ? new Date(date) : date;
  const loc = intlLocale(prefs.locale);

  if (prefs.dateFormat === "yyyy-mm-dd") {
    return new Intl.DateTimeFormat(loc, {
      timeZone: prefs.timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    })
      .format(d)
      .replace(/(\d+)\/(\d+)\/(\d+)/, "$3-$1-$2");
  }

  return new Intl.DateTimeFormat(loc, {
    timeZone: prefs.timezone,
    day: "numeric",
    month: prefs.dateFormat === "dd/mm/yyyy" ? "short" : "numeric",
    year: "numeric",
  }).format(d);
}

export function formatLongDate(
  date: Date | string,
  prefs: Pick<UserPreferences, "locale" | "timezone">
): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return new Intl.DateTimeFormat(intlLocale(prefs.locale), {
    timeZone: prefs.timezone,
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(d);
}

export type MeetingTimeDisplay = {
  dayKey: string;
  dayLabel: string;
  timeLabel: string;
  fullLabel: string;
  isPast: boolean;
};

export function parseMeetingInstant(iso: string | undefined): Date | null {
  if (!iso?.trim()) return null;
  let s = iso.trim();
  // Outlook/Graph puede enviar UTC sin sufijo "Z"; sin zona el navegador usa hora local.
  const hasExplicitTz = /[zZ]$|[+-]\d{2}:\d{2}$/.test(s);
  if (/^\d{4}-\d{2}-\d{2}T/.test(s) && !hasExplicitTz) {
    s = s.replace(/\.\d+$/, "") + "Z";
  }
  const ms = Date.parse(s);
  if (Number.isNaN(ms)) return null;
  return new Date(ms);
}

/** Agrupa y muestra reuniones de calendario en la zona horaria del usuario. */
export function formatMeetingTimeRange(
  inicio: string | undefined,
  fin: string | undefined,
  prefs: Pick<UserPreferences, "locale" | "timezone">,
  options?: { allDay?: boolean; allDayLabel?: string },
): MeetingTimeDisplay {
  const loc = intlLocale(prefs.locale);
  const tz = prefs.timezone || "UTC";
  const start = parseMeetingInstant(inicio);
  const end = parseMeetingInstant(fin);
  const now = Date.now();
  const isPast = end ? end.getTime() < now : start ? start.getTime() < now : false;

  if (!start) {
    const fallback = (inicio || "—").slice(0, 40);
    return {
      dayKey: "unknown",
      dayLabel: fallback,
      timeLabel: "",
      fullLabel: fallback,
      isPast,
    };
  }

  const dayFmt = new Intl.DateTimeFormat(loc, {
    timeZone: tz,
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  const dayKeyFmt = new Intl.DateTimeFormat(loc, {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const dayLabel = dayFmt.format(start);
  const dayKey = dayKeyFmt.format(start);

  if (options?.allDay) {
    const allDay = options.allDayLabel ?? "All day";
    return {
      dayKey,
      dayLabel,
      timeLabel: allDay,
      fullLabel: `${dayLabel} · ${allDay}`,
      isPast,
    };
  }

  const timeFmt = new Intl.DateTimeFormat(loc, {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
  });
  const dateTimeFmt = new Intl.DateTimeFormat(loc, {
    timeZone: tz,
    dateStyle: "medium",
    timeStyle: "short",
  });

  const t0 = timeFmt.format(start);
  const t1 = end ? timeFmt.format(end) : "";
  const timeLabel = t1 ? `${t0} – ${t1}` : t0;
  const fullStart = dateTimeFmt.format(start);
  const fullLabel = end ? `${fullStart} – ${timeFmt.format(end)}` : fullStart;

  return { dayKey, dayLabel, timeLabel, fullLabel, isPast };
}

/** Fecha y hora de reunión en la zona horaria del usuario (p. ej. dossier de calendario). */
export function formatCalendarMeetingInstant(
  iso: string | undefined,
  prefs: Pick<UserPreferences, "locale" | "timezone">,
): string {
  const start = parseMeetingInstant(iso);
  if (!start) return (iso || "").slice(0, 16);
  return new Intl.DateTimeFormat(intlLocale(prefs.locale), {
    timeZone: prefs.timezone || "UTC",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(start);
}
