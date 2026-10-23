"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import BrandLogo from "@/components/BrandLogo";
import {
  clearAuthSession,
  fetchAuthMe,
  getAuthTokenStorageMode,
  getStoredAccessToken,
  readDossierUserPreview,
  writeDossierUserPreview,
} from "@/lib/dossier-api";
import { useTranslation } from "@/providers/PreferencesProvider";
import { useAuthMe, AUTH_ME_CHANGED_EVENT } from "@/hooks/useAuthMe";
import { normalizePlanTier, planAllowsCorporateDossier, planTierLabel } from "@/lib/plans";
import type { TranslationKey } from "@/i18n/types";
import type { TranslateFn } from "@/i18n";

const mutatorOnlyHrefs = new Set([
  "/dashboard/automation",
  "/dashboard/person-research",
  "/dashboard/corporate",
]);

type NavItem = {
  href: string;
  labelKey: TranslationKey;
  icon: React.ReactNode;
};

const navItems: NavItem[] = [
  {
    href: "/dashboard",
    labelKey: "nav.overview",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        <polyline points="9 22 9 12 15 12 15 22" />
      </svg>
    ),
  },
  {
    href: "/dashboard/automation",
    labelKey: "nav.automation",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5 shrink-0">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
      </svg>
    ),
  },
  {
    href: "/dashboard/dossiers",
    labelKey: "nav.dossiers",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    href: "/dashboard/person-research",
    labelKey: "nav.person_research",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
    ),
  },
  {
    href: "/dashboard/corporate",
    labelKey: "nav.corporate",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
        <path d="M3 21h18" />
        <path d="M5 21V7l8-4v18" />
        <path d="M19 21V11l-6-4" />
        <path d="M9 9v.01" />
        <path d="M9 12v.01" />
        <path d="M9 15v.01" />
        <path d="M9 18v.01" />
      </svg>
    ),
  },
  {
    href: "/dashboard/settings",
    labelKey: "nav.settings",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
    ),
  },
];

const adminNavItem: NavItem = {
  href: "/dashboard/admin",
  labelKey: "nav.admin",
  icon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  ),
};

function initialsFromProfile(fullName: string, email: string): string {
  const n = fullName.trim();
  if (n.length >= 1) {
    const parts = n.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      const a = parts[0][0];
      const b = parts[parts.length - 1][0];
      if (a && b) return (a + b).toUpperCase();
    }
    return n.slice(0, 2).toUpperCase();
  }
  const e = email.trim();
  if (e.length >= 2) return e.slice(0, 2).toUpperCase();
  return "?";
}

type FooterProfile = { initials: string; name: string; detail: string };

function buildFooterDetail(
  t: TranslateFn,
  profile: {
    workspace_kind?: "personal" | "work";
    company_name?: string;
    email: string;
    organization_plan?: string;
  },
): string {
  if (profile.workspace_kind === "personal") {
    const plan = normalizePlanTier(profile.organization_plan);
    return t("workspace.personal_plan", { plan: planTierLabel(t, plan) });
  }
  return profile.company_name?.trim() || profile.email;
}

type SidebarProps = {
  id?: string;
  /** Solo por debajo de `md`: la barra se muestra como cajón modal. */
  mobileOpen?: boolean;
  /** Botón de cerrar del cajón móvil. */
  onClose?: () => void;
  /** Se llama al seguir cualquier enlace de la barra (cierra el cajón móvil). */
  onNavigate?: () => void;
};

export default function Sidebar({
  id,
  mobileOpen = false,
  onClose,
  onNavigate,
}: SidebarProps = {}) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useTranslation();
  const { canMutate, user } = useAuthMe();
  const showCorporateNav = planAllowsCorporateDossier(normalizePlanTier(user?.organization_plan));
  const [footer, setFooter] = useState<FooterProfile | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [isPlatformAdmin, setIsPlatformAdmin] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Al abrir el cajón móvil, el foco entra en él.
  useEffect(() => {
    if (mobileOpen) closeButtonRef.current?.focus();
  }, [mobileOpen]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const token = getStoredAccessToken();
      if (token) {
        try {
          const me = await fetchAuthMe();
          if (cancelled) return;
          setIsPlatformAdmin(!!me.is_platform_admin);
          writeDossierUserPreview(
            {
              email: me.email,
              full_name: me.full_name,
              company_name: me.company_name,
              workspace_kind: me.workspace_kind,
              organization_plan: me.organization_plan,
              is_platform_admin: !!me.is_platform_admin,
            },
            getAuthTokenStorageMode()
          );
          const initials = initialsFromProfile(me.full_name, me.email);
          const name = me.full_name.trim() || me.email;
          const detail = buildFooterDetail(t, me);
          setFooter({ initials, name, detail });
        } catch {
          if (cancelled) return;
          setIsPlatformAdmin(false);
          const preview = readDossierUserPreview();
          if (preview) {
            setIsPlatformAdmin(!!preview.is_platform_admin);
            const initials = initialsFromProfile(preview.full_name, preview.email);
            const name = preview.full_name.trim() || preview.email;
            const detail = buildFooterDetail(t, {
              workspace_kind: preview.workspace_kind,
              company_name: preview.company_name,
              email: preview.email,
              organization_plan: preview.organization_plan,
            });
            setFooter({ initials, name, detail });
          } else {
            setFooter({
              initials: "?",
              name: t("overview.anonymous"),
              detail: "",
            });
          }
        }
        return;
      }
    }

    void load();
    window.addEventListener(AUTH_ME_CHANGED_EVENT, load);
    return () => {
      cancelled = true;
      window.removeEventListener(AUTH_ME_CHANGED_EVENT, load);
    };
  }, [t]);

  useEffect(() => {
    if (!menuOpen) return;
    function handlePointerDown(e: MouseEvent) {
      if (!profileMenuRef.current?.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [menuOpen]);

  function handleLogout() {
    clearAuthSession();
    setMenuOpen(false);
    setIsPlatformAdmin(false);
    setFooter(null);
    router.push("/login");
    router.refresh();
  }

  function isActive(href: string) {
    if (href === "/dashboard") return pathname === "/dashboard";
    return pathname.startsWith(href);
  }

  const display = footer ?? {
    initials: "…",
    name: t("common.loading"),
    detail: "",
  };

  return (
    <aside
      id={id}
      role={mobileOpen ? "dialog" : undefined}
      aria-modal={mobileOpen ? true : undefined}
      aria-label={t("nav.sidebar_label")}
      className={[
        "fixed inset-y-0 left-0 z-40 flex w-64 flex-col",
        // Al abrir, `visibility` cambia al instante (si se animara, el cajón seguiría
        // oculto cuando recibe el foco). Al cerrar, cambia tras el deslizamiento.
        "transition-transform duration-200 ease-out motion-reduce:transition-none",
        "md:visible md:translate-x-0",
        mobileOpen
          ? "visible translate-x-0"
          : "max-md:invisible max-md:-translate-x-full max-md:[transition:transform_200ms_ease-out,visibility_0s_linear_200ms]",
      ].join(" ")}
      style={{
        backgroundImage:
          "linear-gradient(180deg, var(--bg-sidebar-start) 0%, var(--bg-sidebar-end) 100%)",
        borderRight: "1px solid var(--border-subtle)",
      }}
    >
      <div
        className="relative flex w-full items-center justify-center px-4 py-6"
        style={{ borderBottom: "1px solid var(--border-subtle)" }}
      >
        {mobileOpen ? (
          <button
            ref={closeButtonRef}
            type="button"
            className="absolute right-2 top-2 flex h-9 w-9 items-center justify-center rounded-lg transition ui-hover-surface md:hidden"
            style={{ color: "var(--text-muted)" }}
            aria-label={t("nav.close_menu")}
            onClick={() => onClose?.()}
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-5 w-5"
              aria-hidden
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        ) : null}
        <Link
          href="/dashboard"
          className="brand-logo-link flex w-full justify-center"
          onClick={() => onNavigate?.()}
        >
          <BrandLogo size="md" />
        </Link>
      </div>

      <nav className="flex-1 px-3 py-4">
        <ul className="flex flex-col gap-1">
          {[...navItems.filter((item) => {
            if (!canMutate && mutatorOnlyHrefs.has(item.href)) return false;
            if (item.href === "/dashboard/corporate" && !showCorporateNav) return false;
            return true;
          }), ...(isPlatformAdmin ? [adminNavItem] : [])].map((item) => {
            const active = isActive(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  onClick={() => onNavigate?.()}
                  className={[
                    "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium leading-snug",
                    "transition-all duration-200 ease-out",
                    active
                      ? "hover:brightness-110"
                      : "ui-hover-surface hover:translate-x-0.5 hover:text-[var(--text-primary)]",
                  ].join(" ")}
                  style={{
                    color: active ? "var(--brand-cyan)" : "var(--text-muted)",
                    backgroundColor: active ? "var(--bg-surface-hover)" : undefined,
                  }}
                >
                  <span
                    className={
                      active
                        ? "shrink-0"
                        : "shrink-0 transition-colors duration-200 group-hover:text-[var(--brand-cyan)]"
                    }
                  >
                    {item.icon}
                  </span>
                  <span className="min-w-0">{t(item.labelKey)}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div
        ref={profileMenuRef}
        className="relative px-4 py-4"
        style={{ borderTop: "1px solid var(--border-subtle)" }}
      >
        <button
          type="button"
          className="flex w-full items-center gap-3 rounded-lg p-1.5 text-left transition ui-hover-surface"
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          aria-label={t("nav.user_menu")}
          onClick={() => setMenuOpen((o) => !o)}
        >
          <div
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
            style={{
              backgroundImage:
                "linear-gradient(135deg, var(--accent-from) 0%, var(--accent-to) 100%)",
            }}
          >
            {display.initials}
          </div>
          <div className="min-w-0 flex-1 flex flex-col">
            <span
              className="truncate text-sm font-semibold"
              style={{ color: "var(--text-primary)" }}
              title={display.name}
            >
              {display.name}
            </span>
            <span
              className="truncate text-xs"
              style={{ color: "var(--text-muted)" }}
              title={display.detail}
            >
              {display.detail}
            </span>
          </div>
          <svg
            viewBox="0 0 24 24"
            width="16"
            height="16"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className={`shrink-0 opacity-60 transition-transform duration-200 ${menuOpen ? "rotate-180" : ""}`}
            style={{ color: "var(--text-muted)" }}
            aria-hidden
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
        {menuOpen ? (
          <div
            className="absolute bottom-full left-2 right-2 z-50 mb-1 overflow-hidden rounded-lg border py-1 shadow-xl"
            role="menu"
            style={{
              borderColor: "var(--border-default)",
              backgroundColor: "var(--bg-surface)",
              boxShadow: "0 -8px 24px rgba(0,0,0,0.35)",
            }}
          >
            <button
              type="button"
              role="menuitem"
              className="flex w-full px-3 py-2.5 text-left text-sm font-medium transition ui-hover-surface"
              style={{ color: "var(--text-primary)" }}
              onClick={() => handleLogout()}
            >
              {t("nav.logout")}
            </button>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
