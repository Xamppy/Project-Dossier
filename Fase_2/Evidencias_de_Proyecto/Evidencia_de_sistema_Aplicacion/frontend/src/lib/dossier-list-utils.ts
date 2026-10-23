import type { FilterValue } from "@/components/dossier/FilterTabs";
import { getCalendarMeetingLabel, readCalendarBlockFromData } from "@/lib/calendar-dossier-meta";
import type { TranslationKey } from "@/i18n/types";
import {
  isDossierFolderEntry,
  type DossierFolderListItem,
  type DossierListEntry,
  type DossierListItem,
} from "@/lib/dossier-api";

export type DossierTimeGroup = "upcoming" | "past" | "other";
export type TypeFilterValue = "all" | "person" | "corporate";
export type DossierViewMode = "all" | "meeting_folders" | "standalone";

export function entryMatchesViewMode(
  entry: DossierListEntry,
  viewMode: DossierViewMode
): boolean {
  if (viewMode === "all") return true;
  if (viewMode === "meeting_folders") return isDossierFolderEntry(entry);
  return !isDossierFolderEntry(entry);
}

export function countEntriesByViewMode(
  items: DossierListEntry[]
): Record<Exclude<DossierViewMode, "all">, number> {
  let meeting_folders = 0;
  let standalone = 0;
  for (const entry of items) {
    if (!isNonEmptyListEntry(entry)) continue;
    if (isDossierFolderEntry(entry)) meeting_folders += 1;
    else standalone += 1;
  }
  return { meeting_folders, standalone };
}

/** Quita un dossier de la lista; si era el último de una carpeta, elimina la carpeta entera. */
export function removeDossierFromListEntries(
  items: DossierListEntry[],
  dossierId: string
): DossierListEntry[] {
  return items
    .map((entry) => {
      if (isDossierFolderEntry(entry)) {
        const dossiers = entry.dossiers.filter((d) => d.id !== dossierId);
        if (dossiers.length === 0) return null;
        return { ...entry, dossiers };
      }
      if (entry.id === dossierId) return null;
      return entry;
    })
    .filter((e): e is DossierListEntry => e !== null);
}

/** Quita un dossier de una carpeta; devuelve null si la carpeta queda vacía. */
export function removeDossierFromFolder(
  folder: DossierFolderListItem,
  dossierId: string
): DossierFolderListItem | null {
  const dossiers = folder.dossiers.filter((d) => d.id !== dossierId);
  if (dossiers.length === 0) return null;
  return { ...folder, dossiers };
}

export function isNonEmptyListEntry(entry: DossierListEntry): boolean {
  if (isDossierFolderEntry(entry)) return entry.dossiers.length > 0;
  return true;
}

export function formatDossierStatusLabel(
  status: string,
  t: (key: TranslationKey) => string
): string {
  if (status === "complete" || status === "completed") return t("dossiers.status_complete");
  if (status === "failed") return t("dossiers.status_failed");
  if (status === "pending" || status === "processing") return t("dossiers.status_pending");
  return status.replace(/_/g, " ");
}

function dossierDataForEntry(entry: DossierListEntry): unknown {
  if (isDossierFolderEntry(entry)) {
    return entry.dossiers[0]?.dossier_data;
  }
  return entry.dossier_data;
}

export function getEntryMeetingStartIso(entry: DossierListEntry): string | null {
  const cal = readCalendarBlockFromData(dossierDataForEntry(entry));
  const inicio = cal?.inicio?.trim();
  return inicio || null;
}

export function isCalendarListEntry(entry: DossierListEntry): boolean {
  if (isDossierFolderEntry(entry)) {
    if ((entry.trigger_source || "").trim() === "calendar") return true;
    return entry.dossiers.some(
      (d) => (d.trigger_source || "").trim() === "calendar" || readCalendarBlockFromData(d.dossier_data)
    );
  }
  return (
    (entry.trigger_source || "").trim() === "calendar" ||
    readCalendarBlockFromData(entry.dossier_data) !== null
  );
}

export function dossierItemMatchesTypeFilter(
  row: DossierListItem,
  typeFilter: TypeFilterValue
): boolean {
  if (typeFilter === "all") return true;
  if (typeFilter === "person") return row.module_kind === "person";
  if (typeFilter === "corporate") return row.module_kind === "corporate";
  return true;
}

/** Filtra entradas de lista; las carpetas de reunión se mantienen si tienen al menos un hijo del tipo. */
export function entryMatchesTypeFilter(
  entry: DossierListEntry,
  typeFilter: TypeFilterValue
): boolean {
  if (typeFilter === "all") return true;
  if (isDossierFolderEntry(entry)) {
    return entry.dossiers.some((d) => dossierItemMatchesTypeFilter(d, typeFilter));
  }
  return dossierItemMatchesTypeFilter(entry, typeFilter);
}

export function classifyDossierEntry(entry: DossierListEntry, nowMs = Date.now()): DossierTimeGroup {
  const iso = getEntryMeetingStartIso(entry);
  if (!iso) return "other";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "other";
  return ms >= nowMs ? "upcoming" : "past";
}

function meetingSortKey(entry: DossierListEntry): string {
  return getEntryMeetingStartIso(entry) || entrySortDate(entry);
}

function entrySortDate(entry: DossierListEntry): string {
  if (isDossierFolderEntry(entry)) {
    return entry.updated_at || entry.created_at || "";
  }
  return entry.updated_at || entry.created_at || "";
}

export function sortListEntriesByDate(items: DossierListEntry[]): DossierListEntry[] {
  return [...items].sort((a, b) => entrySortDate(b).localeCompare(entrySortDate(a)));
}

export function sortListEntriesByMeetingStart(
  items: DossierListEntry[],
  direction: "asc" | "desc" = "asc"
): DossierListEntry[] {
  return [...items].sort((a, b) => {
    const cmp = meetingSortKey(a).localeCompare(meetingSortKey(b));
    return direction === "asc" ? cmp : -cmp;
  });
}

export function groupListEntriesByMeetingTime(items: DossierListEntry[]): {
  upcoming: DossierListEntry[];
  past: DossierListEntry[];
  other: DossierListEntry[];
} {
  const upcoming: DossierListEntry[] = [];
  const past: DossierListEntry[] = [];
  const other: DossierListEntry[] = [];

  for (const entry of items) {
    const group = classifyDossierEntry(entry);
    if (group === "upcoming") upcoming.push(entry);
    else if (group === "past") past.push(entry);
    else other.push(entry);
  }

  return {
    upcoming: sortListEntriesByMeetingStart(upcoming, "asc"),
    past: sortListEntriesByMeetingStart(past, "desc"),
    other: sortListEntriesByDate(other),
  };
}

function entryNeedsUpdate(entry: DossierListEntry): boolean {
  if (isDossierFolderEntry(entry)) {
    return entry.dossiers.some((d) => d.status !== "complete");
  }
  return entry.status !== "complete";
}

export function entryMatchesFilter(entry: DossierListEntry, filter: FilterValue): boolean {
  if (filter === "all") return true;
  if (filter === "active") return classifyDossierEntry(entry) !== "past";
  if (filter === "past") return classifyDossierEntry(entry) === "past";
  if (filter === "needs_update") return entryNeedsUpdate(entry);
  return true;
}

export function entryMatchesQuery(entry: DossierListEntry, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;

  if (isDossierFolderEntry(entry)) {
    const title = (entry.title || "").toLowerCase();
    const meeting = (getCalendarMeetingLabel(entry) || "").toLowerCase();
    if (title.includes(q) || meeting.includes(q)) return true;
    return entry.dossiers.some((d) => dossierMatchesQuery(d, q));
  }
  return dossierMatchesQuery(entry, q);
}

function dossierMatchesQuery(row: DossierListItem, q: string): boolean {
  const name = (row.subject_name || "").toLowerCase();
  const mail = (row.subject_email || "").toLowerCase();
  let companyFromPerson = "";
  const dd = row.dossier_data;
  if (dd && typeof dd === "object" && !Array.isArray(dd)) {
    const pf = (dd as Record<string, unknown>).person_filters;
    if (pf && typeof pf === "object" && !Array.isArray(pf)) {
      const c = (pf as Record<string, unknown>).company;
      if (typeof c === "string") companyFromPerson = c.toLowerCase();
    }
  }
  const meeting = (getCalendarMeetingLabel(row) || "").toLowerCase();
  return (
    name.includes(q) ||
    mail.includes(q) ||
    companyFromPerson.includes(q) ||
    meeting.includes(q)
  );
}

export function countListEntries(items: DossierListEntry[]): {
  all: number;
  active: number;
  past: number;
  needs_update: number;
  complete: number;
} {
  let active = 0;
  let past = 0;
  let needs_update = 0;
  let complete = 0;
  for (const entry of items) {
    const timeGroup = classifyDossierEntry(entry);
    if (timeGroup === "past") past += 1;
    else active += 1;

    if (entryNeedsUpdate(entry)) needs_update += 1;
    else complete += 1;
  }
  return { all: items.length, active, past, needs_update, complete };
}

const DEPTH_LABEL_KEYS: Record<string, TranslationKey> = {
  basic: "depth.option_basic_label",
  standard: "depth.option_standard_label",
  deep: "depth.option_deep_label",
};

export function depthLevelLabel(
  depth: string,
  t: (key: TranslationKey) => string,
): string {
  const key = depth?.trim().toLowerCase();
  const labelKey = key ? DEPTH_LABEL_KEYS[key] : undefined;
  return labelKey ? t(labelKey) : depth;
}
