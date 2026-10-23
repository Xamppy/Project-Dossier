"use client";

import {
  getCalendarMeetingLabel,
  getCalendarProviderLabelKey,
  readCalendarBlockFromData,
} from "@/lib/calendar-dossier-meta";
import { useTranslation } from "@/providers/PreferencesProvider";

type Props = {
  trigger_source?: string | null;
  calendar_meeting?: string | null;
  dossier_data?: unknown;
  compact?: boolean;
};

export default function CalendarMeetingLabel({
  trigger_source,
  calendar_meeting,
  dossier_data,
  compact = false,
}: Props) {
  const { t, preferences } = useTranslation();
  const label = getCalendarMeetingLabel(
    { trigger_source, calendar_meeting, dossier_data },
    preferences,
  );
  if (!label) return null;

  const cal = readCalendarBlockFromData(dossier_data);
  const providerKey = getCalendarProviderLabelKey(cal?.provider);
  const providerLabel = providerKey ? t(providerKey) : null;

  return (
    <p
      className={compact ? "text-xs leading-snug" : "text-sm leading-snug"}
      style={{ color: "var(--text-muted)" }}
      title={providerLabel ? `${t("dossiers.calendar_meeting_from")} ${providerLabel}` : undefined}
    >
      <span aria-hidden className="mr-1">
        📅
      </span>
      <span className="font-medium" style={{ color: "var(--text-secondary)" }}>
        {t("dossiers.calendar_meeting")}:
      </span>{" "}
      {label}
    </p>
  );
}
