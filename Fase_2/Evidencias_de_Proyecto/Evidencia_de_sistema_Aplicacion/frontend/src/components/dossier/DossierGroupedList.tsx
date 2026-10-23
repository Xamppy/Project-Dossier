"use client";

import DossierFolderCard from "@/components/dossier/DossierFolderCard";
import DossierListCard from "@/components/dossier/DossierListCard";
import type { FilterValue } from "@/components/dossier/FilterTabs";
import { isDossierFolderEntry, type DossierListEntry, type DossierListItem } from "@/lib/dossier-api";
import type { DossierViewMode, TypeFilterValue } from "@/lib/dossier-list-utils";
import { useTranslation } from "@/providers/PreferencesProvider";
import type { TranslationKey } from "@/i18n/types";

const MEETING_GRID_CLASS = "grid grid-cols-1 gap-4 sm:grid-cols-2";
const OTHER_GRID_CLASS = "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3";

function renderEntry(
  entry: DossierListEntry,
  typeFilter: TypeFilterValue,
  deletingId: string | null,
  onDeleteDossier: (row: DossierListItem) => void,
  showDelete: boolean,
) {
  if (isDossierFolderEntry(entry)) {
    return (
      <DossierFolderCard
        key={entry.id}
        folder={entry}
        typeFilter={typeFilter}
        deletingId={deletingId}
        onDeleteDossier={onDeleteDossier}
        showDelete={showDelete}
      />
    );
  }
  return (
    <DossierListCard
      key={entry.id}
      dossier={entry}
      deletingId={deletingId}
      onDelete={() => onDeleteDossier(entry)}
      showDelete={showDelete}
    />
  );
}

type SectionProps = {
  titleKey: TranslationKey;
  hintKey?: TranslationKey;
  entries: DossierListEntry[];
  typeFilter: TypeFilterValue;
  deletingId: string | null;
  onDeleteDossier: (row: DossierListItem) => void;
  gridClass?: string;
  showDelete?: boolean;
};

function DossierListSection({
  titleKey,
  hintKey,
  entries,
  typeFilter,
  deletingId,
  onDeleteDossier,
  gridClass = MEETING_GRID_CLASS,
  showDelete = true,
}: SectionProps) {
  const { t } = useTranslation();
  if (entries.length === 0) return null;

  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          {t(titleKey)}
          <span className="ml-2 text-xs font-normal" style={{ color: "var(--text-subtle)" }}>
            ({entries.length})
          </span>
        </h2>
        {hintKey ? (
          <p className="mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>
            {t(hintKey)}
          </p>
        ) : null}
      </div>

      <div className={gridClass}>
        {entries.map((entry) =>
          renderEntry(entry, typeFilter, deletingId, onDeleteDossier, showDelete)
        )}
      </div>
    </section>
  );
}

type Props = {
  groups: {
    upcoming: DossierListEntry[];
    past: DossierListEntry[];
    other: DossierListEntry[];
  };
  flatEntries: DossierListEntry[];
  filter: FilterValue;
  viewMode?: DossierViewMode;
  typeFilter: TypeFilterValue;
  deletingId: string | null;
  onDeleteDossier: (row: DossierListItem) => void;
  showDelete?: boolean;
};

export default function DossierGroupedList({
  groups,
  flatEntries,
  filter,
  viewMode = "meeting_folders",
  typeFilter,
  deletingId,
  onDeleteDossier,
  showDelete = true,
}: Props) {
  if (filter !== "all" || viewMode === "standalone") {
    return (
      <div
        className={
          viewMode === "standalone" || viewMode === "all" ? OTHER_GRID_CLASS : MEETING_GRID_CLASS
        }
      >
        {flatEntries.map((entry) =>
          renderEntry(entry, typeFilter, deletingId, onDeleteDossier, showDelete)
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <DossierListSection
        titleKey="dossiers.section_upcoming"
        hintKey="dossiers.section_upcoming_hint"
        entries={groups.upcoming}
        typeFilter={typeFilter}
        deletingId={deletingId}
        onDeleteDossier={onDeleteDossier}
        showDelete={showDelete}
      />
      <DossierListSection
        titleKey="dossiers.section_past"
        hintKey="dossiers.section_past_hint"
        entries={groups.past}
        typeFilter={typeFilter}
        deletingId={deletingId}
        onDeleteDossier={onDeleteDossier}
        showDelete={showDelete}
      />
      <DossierListSection
        titleKey="dossiers.section_other"
        hintKey="dossiers.section_other_hint"
        entries={groups.other}
        typeFilter={typeFilter}
        deletingId={deletingId}
        onDeleteDossier={onDeleteDossier}
        gridClass={OTHER_GRID_CLASS}
        showDelete={showDelete}
      />
    </div>
  );
}
