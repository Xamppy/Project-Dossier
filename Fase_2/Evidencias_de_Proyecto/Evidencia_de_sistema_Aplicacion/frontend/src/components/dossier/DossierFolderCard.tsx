"use client";

import Link from "next/link";
import CalendarMeetingLabel from "@/components/dossier/CalendarMeetingLabel";
import DeleteDossierIconButton from "@/components/dossier/DeleteDossierIconButton";
import DossierStatusBadge from "@/components/dossier/DossierStatusBadge";
import { formatDate } from "@/lib/format";
import { dossierItemMatchesTypeFilter, depthLevelLabel, type TypeFilterValue } from "@/lib/dossier-list-utils";
import { getCalendarMeetingSubject } from "@/lib/calendar-dossier-meta";
import { stripHtmlToPlainLine } from "@/lib/strip-html";
import type { DossierFolderListItem, DossierListItem } from "@/lib/dossier-api";
import { useTranslation } from "@/providers/PreferencesProvider";

type Props = {
  folder: DossierFolderListItem;
  typeFilter: TypeFilterValue;
  deletingId: string | null;
  onDeleteDossier: (row: DossierListItem) => void;
  showDelete?: boolean;
};

function MeetingFolderIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-7 w-7">
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
      <path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01" strokeLinecap="round" />
    </svg>
  );
}

function moduleLabel(
  row: DossierListItem,
  t: ReturnType<typeof useTranslation>["t"],
  personIndex?: number,
  personTotal?: number,
): string {
  if (row.module_kind === "corporate") return t("overview.calendar_dossier_corporate");
  if (row.module_kind === "person") {
    if (personTotal && personTotal > 1 && personIndex) {
      return `${t("overview.calendar_dossier_person")} ${personIndex}`;
    }
    return t("overview.calendar_dossier_person");
  }
  return t("dossiers.folder_other_dossier");
}

function ChildDossierChip({
  row,
  deletingId,
  onDelete,
  personIndex,
  personTotal,
  showDelete = true,
}: {
  row: DossierListItem;
  deletingId: string | null;
  onDelete: () => void;
  personIndex?: number;
  personTotal?: number;
  showDelete?: boolean;
}) {
  const { t } = useTranslation();
  const isFailed = row.status === "failed";
  const statusMsg = row.status_message?.trim();

  return (
    <div
      className="ui-dossier-chip relative flex min-w-0 flex-1 flex-col gap-2 rounded-lg border p-3 pr-10"
      style={{
        borderColor: isFailed ? "rgba(248,113,113,0.35)" : "var(--border-default)",
        backgroundColor: "var(--bg-input)",
      }}
    >
      {showDelete ? (
        <DeleteDossierIconButton
          isDeleting={deletingId === row.id}
          onClick={onDelete}
          className="absolute right-1 top-1"
        />
      ) : null}

      <div className="flex items-start justify-between gap-2">
        <span
          className="text-[11px] font-semibold uppercase tracking-wide"
          style={{ color: "var(--text-subtle)" }}
        >
          {moduleLabel(row, t, personIndex, personTotal)}
        </span>
        <DossierStatusBadge status={row.status} />
      </div>

      <Link
        href={`/dashboard/dossiers/${row.id}`}
        className="ui-dossier-chip__link min-w-0 text-left"
      >
        <span
          className="ui-dossier-chip__title block truncate text-sm font-semibold"
          style={{ color: "var(--text-primary)" }}
        >
          {stripHtmlToPlainLine(row.subject_name || row.subject_email) || "—"}
        </span>
        <span className="mt-0.5 block text-xs capitalize" style={{ color: "var(--text-muted)" }}>
          {depthLevelLabel(row.depth_level, t)}
        </span>
        {isFailed && statusMsg ? (
          <span className="mt-1 block text-xs leading-snug" style={{ color: "var(--text-muted)" }}>
            {statusMsg}
          </span>
        ) : null}
      </Link>
    </div>
  );
}

export default function DossierFolderCard({
  folder,
  typeFilter,
  deletingId,
  onDeleteDossier,
  showDelete = true,
}: Props) {
  const { t, preferences } = useTranslation();
  const dateRaw = folder.updated_at || folder.created_at;
  const dateLabel = dateRaw ? formatDate(dateRaw, preferences) : null;
  const allComplete = folder.dossiers.every((d) => d.status === "complete");
  const folderStatus = allComplete ? "complete" : folder.status;

  if (folder.dossiers.length === 0) {
    return null;
  }

  const corporate = folder.dossiers.find((d) => d.module_kind === "corporate");
  const persons = folder.dossiers.filter((d) => d.module_kind === "person");
  const ordered = [
    ...(corporate ? [corporate] : []),
    ...persons,
    ...folder.dossiers.filter(
      (d) => d.id !== corporate?.id && !persons.some((p) => p.id === d.id)
    ),
  ]
    .filter((d) => dossierItemMatchesTypeFilter(d, typeFilter));
  const dossierCountLabel =
    typeFilter === "all"
      ? folder.dossiers.length === 1
        ? t("dossiers.folder_one_dossier")
        : t("dossiers.folder_n_dossiers")
      : ordered.length === 1
        ? t("dossiers.folder_one_dossier")
        : t("dossiers.folder_n_dossiers");
  const dossierCount = typeFilter === "all" ? folder.dossiers.length : ordered.length;
  const displayTitle = stripHtmlToPlainLine(
    getCalendarMeetingSubject({
      calendar_meeting: folder.calendar_meeting,
      dossier_data: folder.dossiers[0]?.dossier_data,
    }) || folder.title
  );

  return (
    <article
      className="ui-dossier-card group h-full rounded-xl border"
      style={{
        borderColor: "var(--border-default)",
        backgroundImage:
          "linear-gradient(180deg, var(--bg-card-start) 0%, var(--bg-card-end) 100%)",
      }}
    >
      <div className="flex flex-col gap-4 p-4">
        <div className="flex min-w-0 gap-3">
          <div
            className="ui-dossier-card__icon flex h-14 w-14 shrink-0 items-center justify-center self-start rounded-xl"
            style={{
              backgroundColor: "var(--bg-surface-strong)",
              color: "var(--accent-from)",
            }}
            aria-hidden
          >
            <MeetingFolderIcon />
          </div>
          <div className="min-w-0 flex-1">
            <p
              className="ui-dossier-card__title text-base font-semibold leading-snug"
              style={{ color: "var(--text-primary)" }}
            >
              {displayTitle || "—"}
            </p>
            <CalendarMeetingLabel
              trigger_source={folder.trigger_source}
              calendar_meeting={folder.calendar_meeting}
              dossier_data={folder.dossiers[0]?.dossier_data}
              compact
            />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <DossierStatusBadge status={folderStatus} />
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                {dossierCount} {dossierCountLabel}
              </span>
              {dateLabel ? (
                <span className="text-xs" style={{ color: "var(--text-subtle)" }}>
                  · {dateLabel}
                </span>
              ) : null}
            </div>
          </div>
        </div>

        <div
          className={
            ordered.length === 1
              ? "grid grid-cols-1 gap-2"
              : "grid grid-cols-1 gap-2 sm:grid-cols-2"
          }
        >
          {ordered.map((row) => {
            const personIdx =
              row.module_kind === "person"
                ? persons.findIndex((p) => p.id === row.id) + 1
                : undefined;
            return (
            <ChildDossierChip
              key={row.id}
              row={row}
              deletingId={deletingId}
              onDelete={() => onDeleteDossier(row)}
              personIndex={personIdx || undefined}
              personTotal={persons.length > 1 ? persons.length : undefined}
              showDelete={showDelete}
            />
            );
          })}
        </div>
      </div>
    </article>
  );
}
