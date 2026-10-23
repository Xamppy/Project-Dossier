"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  fetchDossiersFromApi,
  getStoredAccessToken,
  isDossierFolderEntry,
  type DossierListEntry,
} from "@/lib/dossier-api";

const STORAGE_KEY = "dossier_notifications_v1";
const BASELINE_KEY = "dossier_notifications_baseline_v1";
const POLL_MS = 15000;
const MAX_NOTIFICATIONS = 40;

export type DossierNotification = {
  id: string;
  kind: "dossier" | "folder";
  title: string;
  status: string;
  createdAt: string;
  href: string;
  /** `manual` (lo pidió el usuario) o `automated` (calendario / automatización). */
  origin: "manual" | "automated";
  read: boolean;
};

type NotificationsContextValue = {
  notifications: DossierNotification[];
  unreadCount: number;
  markAllRead: () => void;
  markRead: (id: string) => void;
  clearAll: () => void;
  refresh: () => void;
};

const NotificationsContext = createContext<NotificationsContextValue | null>(null);

function loadStored(): DossierNotification[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (n): n is DossierNotification =>
        typeof n === "object" && n !== null && typeof (n as DossierNotification).id === "string",
    );
  } catch {
    return [];
  }
}

function saveStored(list: DossierNotification[]) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, MAX_NOTIFICATIONS)));
  } catch {
    /* ignore */
  }
}

function loadBaseline(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(BASELINE_KEY);
  } catch {
    return null;
  }
}

function saveBaseline(iso: string) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(BASELINE_KEY, iso);
  } catch {
    /* ignore */
  }
}

function notificationOrigin(trigger_source: string | null | undefined): "manual" | "automated" {
  return trigger_source && trigger_source !== "manual" ? "automated" : "manual";
}

function entryToNotification(entry: DossierListEntry): DossierNotification | null {
  if (isDossierFolderEntry(entry)) {
    if (!entry.created_at) return null;
    const title = entry.calendar_meeting || entry.title || "Reunión";
    return {
      id: `folder:${entry.id}`,
      kind: "folder",
      title,
      status: entry.status,
      createdAt: entry.created_at,
      href: `/dashboard/dossiers/folder/${entry.id}`,
      origin: notificationOrigin(entry.trigger_source),
      read: false,
    };
  }
  if (!entry.created_at) return null;
  return {
    id: `dossier:${entry.id}`,
    kind: "dossier",
    title: entry.calendar_meeting || entry.subject_name || "Dossier",
    status: entry.status,
    createdAt: entry.created_at,
    href: `/dashboard/dossiers/${entry.id}`,
    origin: notificationOrigin(entry.trigger_source),
    read: false,
  };
}

function maxCreatedAt(list: DossierNotification[]): string {
  return list.reduce((max, n) => (n.createdAt > max ? n.createdAt : max), "1970-01-01T00:00:00Z");
}

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<DossierNotification[]>(() => loadStored());
  const baselineRef = useRef<string | null>(loadBaseline());

  const poll = useCallback(async () => {
    if (!getStoredAccessToken()) return;
    let entries: DossierListEntry[];
    try {
      const res = await fetchDossiersFromApi(25);
      entries = res.items ?? [];
    } catch {
      return;
    }

    const fresh = entries
      .map(entryToNotification)
      .filter((n): n is DossierNotification => n !== null);

    if (baselineRef.current === null) {
      const baseline = fresh.length ? maxCreatedAt(fresh) : new Date().toISOString();
      baselineRef.current = baseline;
      saveBaseline(baseline);
      return;
    }

    const baseline = baselineRef.current;
    setNotifications((prev) => {
      const freshById = new Map(fresh.map((n) => [n.id, n]));
      const known = new Set(prev.map((n) => n.id));
      const refreshed = prev.map((n) => {
        const next = freshById.get(n.id);
        return next ? { ...n, ...next, read: n.read } : n;
      });
      const toAdd = fresh
        .filter((n) => !known.has(n.id) && n.createdAt > baseline)
        .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
      const merged = [...toAdd, ...refreshed].slice(0, MAX_NOTIFICATIONS);
      if (
        toAdd.length === 0 &&
        refreshed.every((n, idx) => n === prev[idx])
      ) {
        return prev;
      }
      saveStored(merged);
      return merged;
    });
  }, []);

  useEffect(() => {
    void poll();
    const timer = window.setInterval(() => void poll(), POLL_MS);
    const onFocus = () => void poll();
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [poll]);

  const markAllRead = useCallback(() => {
    setNotifications((prev) => {
      const next = prev.map((n) => (n.read ? n : { ...n, read: true }));
      saveStored(next);
      return next;
    });
  }, []);

  const markRead = useCallback((id: string) => {
    setNotifications((prev) => {
      const next = prev.map((n) => (n.id === id ? { ...n, read: true } : n));
      saveStored(next);
      return next;
    });
  }, []);

  const clearAll = useCallback(() => {
    const now = new Date().toISOString();
    setNotifications([]);
    saveStored([]);
    baselineRef.current = now;
    saveBaseline(now);
  }, []);

  const unreadCount = useMemo(
    () => notifications.reduce((acc, n) => acc + (n.read ? 0 : 1), 0),
    [notifications],
  );

  const value = useMemo(
    () => ({ notifications, unreadCount, markAllRead, markRead, clearAll, refresh: poll }),
    [notifications, unreadCount, markAllRead, markRead, clearAll, poll],
  );

  return (
    <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>
  );
}

export function useNotifications(): NotificationsContextValue {
  const ctx = useContext(NotificationsContext);
  if (!ctx) {
    throw new Error("useNotifications debe usarse dentro de NotificationsProvider");
  }
  return ctx;
}
