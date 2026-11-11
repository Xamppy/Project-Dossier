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
import { AUTH_ME_CHANGED_EVENT } from "@/hooks/useAuthMe";
import {
  fetchDossiersFromApi,
  getStoredAccessToken,
  isDossierFolderEntry,
  type DossierListEntry,
} from "@/lib/dossier-api";
import {
  openDossierNotificationsStream,
  type DossierNotificationsStreamSubscription,
} from "@/lib/dossier-notifications-stream";
import { showDossierNotification } from "@/lib/browser-notifications";
import { reconnectDelay } from "@/lib/reconnect-backoff";

const STORAGE_KEY = "dossier_notifications_v1";
const BASELINE_KEY = "dossier_notifications_baseline_v1";
const MAX_NOTIFICATIONS = 40;
// Mismo tamaño que el evento del canal (`LIMITE_LISTA` en el backend).
const LIST_LIMIT = 25;

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

/** Igualdad por campos: el canal entrega objetos nuevos aunque nada haya cambiado. */
function sameNotification(a: DossierNotification, b: DossierNotification | undefined): boolean {
  if (!b) return false;
  return (
    a.id === b.id &&
    a.kind === b.kind &&
    a.title === b.title &&
    a.status === b.status &&
    a.createdAt === b.createdAt &&
    a.href === b.href &&
    a.origin === b.origin &&
    a.read === b.read
  );
}

function maxCreatedAt(list: DossierNotification[]): string {
  return list.reduce((max, n) => (n.createdAt > max ? n.createdAt : max), "1970-01-01T00:00:00Z");
}

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<DossierNotification[]>(() => loadStored());
  const baselineRef = useRef<string | null>(loadBaseline());
  // Ids ya avisados: un mismo dossier no dispara dos avisos del navegador.
  const avisadosRef = useRef<Set<string>>(new Set(notifications.map((n) => n.id)));

  // Aplica una lista de dossiers (del canal o de `refresh`) a las notificaciones.
  const applyEntries = useCallback((entries: DossierListEntry[]) => {
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
    // Informe beta: aviso del sistema operativo por cada dossier nuevo (si está activado).
    for (const n of fresh) {
      if (n.createdAt > baseline && !avisadosRef.current.has(n.id)) {
        avisadosRef.current.add(n.id);
        showDossierNotification(n.title, n.status, n.href);
      }
    }
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
        refreshed.every((n, idx) => sameNotification(n, prev[idx]))
      ) {
        return prev;
      }
      saveStored(merged);
      return merged;
    });
  }, []);

  // Lectura puntual a demanda. No hay sondeo: la lista llega por el canal (S5.2).
  const refresh = useCallback(async () => {
    if (!getStoredAccessToken()) return;
    try {
      const res = await fetchDossiersFromApi(LIST_LIMIT);
      applyEntries(res.items ?? []);
    } catch {
      /* sin red o sin sesión: el canal se recupera solo */
    }
  }, [applyEntries]);

  // Canal en vivo (S5.2) con reconexión y retroceso progresivo (S5.3).
  useEffect(() => {
    let disposed = false;
    let stream: DossierNotificationsStreamSubscription | null = null;
    let timer: number | null = null;
    // Intentos fallidos seguidos; vuelve a 0 cuando llegan datos.
    let attempt = 0;

    function cancelTimer() {
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
    }

    function connect() {
      cancelTimer();
      // Sin sesión no se abre: se reintenta cuando cambie (AUTH_ME_CHANGED_EVENT).
      if (disposed || stream || !getStoredAccessToken()) return;
      let current: DossierNotificationsStreamSubscription | null = null;
      current = openDossierNotificationsStream({
        onList: (list) => {
          if (disposed || stream !== current) return;
          attempt = 0;
          applyEntries(list.items ?? []);
        },
        onError: (error) => {
          if (disposed || stream !== current) return;
          stream = null;
          // Sesión vencida o sin acceso: reintentar no lo arregla.
          if (error.kind === "unauthorized" || error.kind === "forbidden") return;
          const delay = reconnectDelay(attempt);
          attempt += 1;
          timer = window.setTimeout(connect, delay);
        },
      });
      stream = current;
    }

    function close() {
      cancelTimer();
      stream?.close();
      stream = null;
    }

    // La red volvió: no se espera el retroceso pendiente.
    function onOnline() {
      if (stream) return;
      attempt = 0;
      connect();
    }

    // Otra sesión u organización: el canal anterior no sirve.
    function onSessionChange() {
      close();
      attempt = 0;
      connect();
    }

    connect();
    window.addEventListener("online", onOnline);
    window.addEventListener(AUTH_ME_CHANGED_EVENT, onSessionChange);
    return () => {
      disposed = true;
      close();
      window.removeEventListener("online", onOnline);
      window.removeEventListener(AUTH_ME_CHANGED_EVENT, onSessionChange);
    };
  }, [applyEntries]);

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
    () => ({
      notifications,
      unreadCount,
      markAllRead,
      markRead,
      clearAll,
      refresh: () => void refresh(),
    }),
    [notifications, unreadCount, markAllRead, markRead, clearAll, refresh],
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
