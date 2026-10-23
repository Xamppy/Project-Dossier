"use client";

import Link from "next/link";
import CalendarMeetingLabel from "@/components/dossier/CalendarMeetingLabel";
import DeleteDossierIconButton from "@/components/dossier/DeleteDossierIconButton";
import DossierStatusBadge from "@/components/dossier/DossierStatusBadge";
import { formatDate } from "@/lib/format";
import { depthLevelLabel } from "@/lib/dossier-list-utils";
import type { DossierListItem } from "@/lib/dossier-api";
import { stripHtmlToPlainLine } from "@/lib/strip-html";
import { useTranslation } from "@/providers/PreferencesProvider";

type Props = {
  dossier: DossierListItem;
  deletingId: string | null;
  onDelete: () => void;
  showDelete?: boolean;
};

function moduleIcon(kind: DossierListItem["module_kind"]) {
  if (kind === "corporate") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
        <path d="M3 21h18" />
        <path d="M5 21V7l8-4v18" />
        <path d="M19 21V11l-6-4" />
      </svg>
    );
  }
  if (kind === "person") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

export default function DossierListCard({ dossier, deletingId, onDelete, showDelete = true }: Props) {
  const { t, preferences } = useTranslation();
  const title = stripHtmlToPlainLine(dossier.subject_name || dossier.subject_email) || "—";
  const dateRaw = dossier.updated_at || dossier.created_at;
  const dateLabel = dateRaw ? formatDate(dateRaw, preferences) : null;
  const isDeleting = deletingId === dossier.id;

  return (
    <article
      className="ui-dossier-card group relative h-full rounded-xl border"
      style={{
        borderColor: "var(--border-default)",
        backgroundImage:
          "linear-gradient(180deg, var(--bg-card-start) 0%, var(--bg-card-end) 100%)",
      }}
    >
      <Link
        href={`/dashboard/dossiers/${dossier.id}`}
        className="flex h-full gap-3 p-4 pr-12 sm:items-start"
      >
        <div
          className="ui-dossier-card__icon flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
          style={{
            backgroundColor: "var(--bg-surface-strong)",
            color: "var(--accent-from)",
          }}
        >
          {moduleIcon(dossier.module_kind)}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start gap-2 gap-y-1">
            <h3
              className="ui-dossier-card__title text-sm font-semibold leading-snug"
              style={{ color: "var(--text-primary)" }}
            >
              {title}
            </h3>
            <DossierStatusBadge status={dossier.status} />
          </div>

          {dossier.subject_email && dossier.subject_name ? (
            <p className="mt-0.5 truncate text-xs" style={{ color: "var(--text-muted)" }}>
              {dossier.subject_email}
            </p>
          ) : null}

          <CalendarMeetingLabel
            trigger_source={dossier.trigger_source}
            calendar_meeting={dossier.calendar_meeting}
            dossier_data={dossier.dossier_data}
            compact
          />

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" style={{ color: "var(--text-subtle)" }}>
            <span className="capitalize">{depthLevelLabel(dossier.depth_level, t)}</span>
            {dateLabel ? <span>{dateLabel}</span> : null}
          </div>
        </div>
      </Link>

      {showDelete ? (
        <DeleteDossierIconButton
          isDeleting={isDeleting}
          onClick={onDelete}
          className="absolute right-2 top-2"
        />
      ) : null}
    </article>
  );
}
