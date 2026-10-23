"use client";

import FilterTabs, { type FilterValue } from "@/components/dossier/FilterTabs";
import type { DossierViewMode } from "@/lib/dossier-list-utils";
import { useTranslation } from "@/providers/PreferencesProvider";

type FilterTab = { value: FilterValue; label: string; count: number };

function FilterIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
    </svg>
  );
}

export function DossierFiltersToggle({
  open,
  onToggle,
  hasActiveFilters,
}: {
  open: boolean;
  onToggle: () => void;
  hasActiveFilters: boolean;
}) {
  const { t } = useTranslation();

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-label={t("dossiers.filters_button")}
      className={[
        "ui-dossier-filters-toggle flex h-11 shrink-0 items-center gap-2 rounded-lg border px-3.5 text-sm font-medium",
        open ? "border-[var(--accent-from)]" : "",
      ].join(" ")}
      style={{
        borderColor: open ? undefined : "var(--border-default)",
        backgroundColor: open ? "var(--bg-surface-hover)" : "var(--bg-input)",
        color: open ? "var(--brand-cyan)" : "var(--text-secondary)",
      }}
    >
      <FilterIcon />
      <span className="hidden sm:inline">{t("dossiers.filters_button")}</span>
      {hasActiveFilters ? (
        <span
          className="h-2 w-2 rounded-full"
          style={{ backgroundColor: "var(--accent-from)" }}
          aria-hidden
        />
      ) : null}
    </button>
  );
}

export function DossierFiltersPanel({
  filter,
  onFilterChange,
  viewMode,
  onViewModeChange,
  filterTabs,
}: {
  filter: FilterValue;
  onFilterChange: (value: FilterValue) => void;
  viewMode: DossierViewMode;
  onViewModeChange: (value: DossierViewMode) => void;
  filterTabs: FilterTab[];
}) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <FilterTabs active={filter} onChange={onFilterChange} tabs={filterTabs} />
      <div className="flex shrink-0 items-center gap-2 sm:ml-auto">
        <span className="shrink-0 text-xs font-medium" style={{ color: "var(--text-muted)" }}>
          {t("dossiers.filter_type_label")}
        </span>
        <select
          value={viewMode}
          onChange={(e) => onViewModeChange(e.target.value as DossierViewMode)}
          className="ui-settings-select ui-dossier-type-select"
          aria-label={t("dossiers.filter_type_label")}
        >
          <option value="all">{t("dossiers.filter_type_all")}</option>
          <option value="meeting_folders">{t("dossiers.view_meeting_folders")}</option>
          <option value="standalone">{t("dossiers.view_standalone")}</option>
        </select>
      </div>
    </div>
  );
}
