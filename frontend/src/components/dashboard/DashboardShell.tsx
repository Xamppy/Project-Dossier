"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import BrandLogo from "@/components/BrandLogo";
import Sidebar from "@/components/dashboard/Sidebar";
import NotificationBell from "@/components/dashboard/NotificationBell";
import { useTranslation } from "@/providers/PreferencesProvider";

export const DASHBOARD_SIDEBAR_ID = "dashboard-sidebar";

/** Mismo valor que el breakpoint `md` de Tailwind (48rem). */
const DESKTOP_MEDIA_QUERY = "(min-width: 48rem)";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Armazón del dashboard.
 *
 * Desde `md` la barra lateral queda fija a la izquierda y el contenido se
 * desplaza 16rem (`md:ml-64`). Por debajo de `md` la barra se oculta y se abre
 * como cajón con el botón de menú de la cabecera móvil.
 */
export default function DashboardShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const [lastPathname, setLastPathname] = useState(pathname);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  // Cerrar al navegar: si la ruta cambió desde el último render, el cajón se cierra.
  if (pathname !== lastPathname) {
    setLastPathname(pathname);
    setNavOpen(false);
  }

  const closeNav = useCallback((restoreFocus: boolean) => {
    setNavOpen(false);
    if (restoreFocus) menuButtonRef.current?.focus();
  }, []);

  // Escape cierra; Tab no sale del cajón mientras está abierto.
  useEffect(() => {
    if (!navOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        closeNav(true);
        return;
      }
      if (e.key !== "Tab") return;
      const drawer = document.getElementById(DASHBOARD_SIDEBAR_ID);
      if (!drawer) return;
      const focusables = Array.from(drawer.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || !drawer.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (active === last || !drawer.contains(active))) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [navOpen, closeNav]);

  // Si la ventana crece hasta escritorio con el cajón abierto, se cierra.
  useEffect(() => {
    if (!navOpen || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(DESKTOP_MEDIA_QUERY);
    function handleChange(e: MediaQueryListEvent) {
      if (e.matches) setNavOpen(false);
    }
    media.addEventListener?.("change", handleChange);
    return () => media.removeEventListener?.("change", handleChange);
  }, [navOpen]);

  return (
    <div
      className="flex min-h-screen flex-col md:flex-row"
      style={{ backgroundColor: "var(--bg-page)" }}
    >
      <header
        className="sticky top-0 z-30 flex h-16 items-center gap-3 px-4 md:hidden"
        style={{
          backgroundColor: "var(--bg-page)",
          borderBottom: "1px solid var(--border-subtle)",
        }}
      >
        <button
          ref={menuButtonRef}
          type="button"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition ui-hover-surface"
          style={{ color: "var(--text-primary)" }}
          aria-label={t("nav.open_menu")}
          aria-expanded={navOpen}
          aria-controls={DASHBOARD_SIDEBAR_ID}
          onClick={() => setNavOpen(true)}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-6 w-6"
            aria-hidden
          >
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <Link href="/dashboard" className="brand-logo-link flex w-36 min-w-0">
          <BrandLogo size="sm" />
        </Link>
      </header>

      {navOpen ? (
        <div
          data-testid="dashboard-sidebar-backdrop"
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          aria-hidden
          onClick={() => closeNav(true)}
        />
      ) : null}

      <Sidebar
        id={DASHBOARD_SIDEBAR_ID}
        mobileOpen={navOpen}
        onClose={() => closeNav(true)}
        onNavigate={() => closeNav(false)}
      />
      <NotificationBell />
      <main className="min-w-0 flex-1 md:ml-64">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 md:py-10 lg:px-10">{children}</div>
      </main>
    </div>
  );
}
