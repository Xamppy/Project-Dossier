"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useNotifications, type DossierNotification } from "@/providers/NotificationsProvider";
import { useTranslation } from "@/providers/PreferencesProvider";
import { formatCalendarMeetingInstant } from "@/lib/format";

function BellIcon({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

function statusTone(status: string): { dot: string; key: "ready" | "failed" | "pending" } {
  const s = (status || "").toLowerCase();
  if (s === "failed" || s === "error") return { dot: "var(--status-error)", key: "failed" };
  if (s === "complete" || s === "completed" || s === "ready") return { dot: "var(--status-success)", key: "ready" };
  return { dot: "var(--status-warning)", key: "pending" };
}

function NotificationRow({
  n,
  onClick,
}: {
  n: DossierNotification;
  onClick: () => void;
}) {
  const { t, preferences } = useTranslation();
  const tone = statusTone(n.status);
  const createdLabel = n.createdAt
    ? formatCalendarMeetingInstant(n.createdAt, preferences)
    : "";

  return (
    <Link
      href={n.href}
      onClick={onClick}
      className={[
        "group flex min-w-0 items-start gap-3 border-b px-4 py-3",
        "transition-colors duration-200 ease-out ui-hover-surface",
        n.read ? "border-l-2 border-l-transparent" : "border-l-2 border-l-[var(--accent-from)]",
      ].join(" ")}
      style={{
        backgroundColor: n.read ? "var(--bg-panel)" : "var(--bg-panel-muted)",
        borderBottomColor: "var(--border-default)",
      }}
    >
      <span
        className="mt-1.5 h-2 w-2 shrink-0 rounded-full transition-transform duration-200 group-hover:scale-125"
        style={{
          backgroundColor: tone.dot,
          boxShadow: n.read ? undefined : `0 0 0 3px color-mix(in srgb, ${tone.dot} 25%, transparent)`,
        }}
        aria-hidden
      />
      <span className="min-w-0 flex-1">
        <span className="flex min-w-0 items-center gap-2">
          <span
            className="min-w-0 flex-1 truncate text-sm font-medium transition-colors duration-200 group-hover:text-[var(--brand-cyan)]"
            style={{ color: "var(--text-primary)" }}
          >
            {n.title}
          </span>
          <span
            className="shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide transition-opacity duration-200 group-hover:opacity-90"
            style={{
              color: n.origin === "automated" ? "var(--alert-info-text)" : "var(--text-muted)",
              backgroundColor:
                n.origin === "automated" ? "var(--alert-info-bg)" : "var(--bg-input)",
            }}
          >
            {n.origin === "automated"
              ? t("notifications.automated")
              : t("notifications.manual")}
          </span>
        </span>
        <span
          className="mt-0.5 block text-xs transition-colors duration-200 group-hover:text-[var(--text-secondary)]"
          style={{ color: "var(--text-muted)" }}
        >
          {t(`notifications.status_${tone.key}`)}
          {createdLabel ? ` · ${createdLabel}` : ""}
        </span>
      </span>
      <svg
        viewBox="0 0 24 24"
        width="14"
        height="14"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        className="mt-1 shrink-0 opacity-0 transition-opacity duration-200 group-hover:opacity-60"
        style={{ color: "var(--text-subtle)" }}
        aria-hidden
      >
        <polyline points="9 18 15 12 9 6" />
      </svg>
    </Link>
  );
}

export default function NotificationBell() {
  const { t } = useTranslation();
  const { notifications, unreadCount, markAllRead, markRead, clearAll } = useNotifications();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  function toggle() {
    setOpen((v) => {
      const next = !v;
      if (next && unreadCount > 0) {
        window.setTimeout(() => markAllRead(), 1200);
      }
      return next;
    });
  }

  return (
    <div ref={containerRef} className="fixed right-6 top-4 z-50">
      <button
        type="button"
        onClick={toggle}
        aria-label={t("notifications.aria")}
        aria-expanded={open}
        className={[
          "group relative flex h-10 w-10 items-center justify-center rounded-full border shadow-md",
          "transition-all duration-200 ease-out ui-hover-surface hover:scale-105",
          open
            ? "scale-105 border-[var(--accent-from)] text-[var(--brand-cyan)]"
            : "hover:border-[var(--accent-from)] hover:text-[var(--brand-cyan)]",
        ].join(" ")}
        style={{
          borderColor: open ? undefined : "var(--border-default)",
          backgroundColor: open ? "var(--bg-surface-hover)" : "var(--bg-panel)",
          color: "var(--text-primary)",
        }}
      >
        <span
          className={[
            "transition-all duration-200",
            open ? "text-[var(--brand-cyan)]" : "group-hover:text-[var(--brand-cyan)]",
          ].join(" ")}
        >
          <BellIcon />
        </span>
        {unreadCount > 0 && (
          <span
            className={[
              "absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full px-1",
              "text-[11px] font-bold text-white transition-transform duration-200",
              open ? "scale-110" : "group-hover:scale-110",
            ].join(" ")}
            style={{ backgroundColor: "#ef4444" }}
          >
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          className="notification-panel-enter absolute right-0 mt-2 w-80 overflow-hidden rounded-xl border shadow-xl"
          style={{
            borderColor: "var(--border-strong)",
            backgroundColor: "var(--bg-panel)",
            boxShadow: "0 16px 40px rgba(10, 20, 40, 0.22)",
          }}
        >
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{
              borderBottom: "1px solid var(--border-default)",
              backgroundImage:
                "linear-gradient(180deg, var(--bg-card-start) 0%, var(--bg-panel) 100%)",
            }}
          >
            <span className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              {t("notifications.title")}
              {unreadCount > 0 ? (
                <span
                  className="rounded-full px-1.5 py-0.5 text-[10px] font-bold"
                  style={{
                    color: "var(--brand-cyan)",
                    backgroundColor: "color-mix(in srgb, var(--accent-from) 18%, transparent)",
                  }}
                >
                  {unreadCount}
                </span>
              ) : null}
            </span>
            {notifications.length > 0 && (
              <button
                type="button"
                onClick={() => clearAll()}
                className="ui-hover-danger rounded-md px-2 py-1 text-xs font-medium transition-colors duration-200"
                style={{ color: "var(--text-muted)" }}
              >
                {t("notifications.clear_all")}
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-x-hidden overflow-y-auto" style={{ backgroundColor: "var(--bg-panel)" }}>
            {notifications.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
                <div
                  className="flex h-11 w-11 items-center justify-center rounded-full"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    color: "var(--text-subtle)",
                  }}
                >
                  <BellIcon className="h-5 w-5 opacity-60" />
                </div>
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  {t("notifications.empty")}
                </p>
              </div>
            ) : (
              notifications.map((n) => (
                <NotificationRow
                  key={n.id}
                  n={n}
                  onClick={() => {
                    markRead(n.id);
                    setOpen(false);
                  }}
                />
              ))
            )}
          </div>

          <Link
            href="/dashboard/dossiers"
            onClick={() => setOpen(false)}
            className="group flex items-center justify-center gap-1.5 px-4 py-3 text-center text-xs font-semibold transition-all duration-200 ease-out ui-hover-surface hover:text-[var(--brand-cyan)]"
            style={{
              color: "var(--accent-from)",
              borderTop: "1px solid var(--border-default)",
              backgroundColor: "var(--bg-panel)",
            }}
          >
            {t("notifications.view_all")}
            <svg
              viewBox="0 0 24 24"
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="transition-transform duration-200 group-hover:translate-x-0.5"
              aria-hidden
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </Link>
        </div>
      )}
    </div>
  );
}
