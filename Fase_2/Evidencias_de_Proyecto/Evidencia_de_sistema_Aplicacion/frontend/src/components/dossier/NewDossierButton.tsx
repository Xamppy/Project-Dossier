"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useAuthMe } from "@/hooks/useAuthMe";
import { normalizePlanTier, planAllowsCorporateDossier } from "@/lib/plans";
import { useTranslation } from "@/providers/PreferencesProvider";

type NewDossierButtonProps = {
  className?: string;
};

function PersonIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function CorporateIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
      <path d="M3 21h18" />
      <path d="M5 21V7l8-4v18" />
      <path d="M19 21V11l-6-4" />
    </svg>
  );
}

export default function NewDossierButton({ className = "" }: NewDossierButtonProps) {
  const { t } = useTranslation();
  const { canMutate, loading, user } = useAuthMe();
  const showCorporate = planAllowsCorporateDossier(normalizePlanTier(user?.organization_plan));
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const options = [
    {
      href: "/dashboard/person-research",
      label: t("btn.new_dossier_person"),
      desc: t("quick.person_research_desc"),
      icon: <PersonIcon />,
    },
    ...(showCorporate
      ? [
          {
            href: "/dashboard/corporate",
            label: t("btn.new_dossier_corporate"),
            desc: t("quick.corporate_desc"),
            icon: <CorporateIcon />,
          },
        ]
      : []),
  ] as const;

  if (!loading && !canMutate) return null;

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="ui-new-dossier-btn inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold text-white"
        style={{
          backgroundImage:
            "linear-gradient(135deg, var(--accent-from) 0%, var(--accent-to) 100%)",
          boxShadow: "0 10px 25px rgba(0, 183, 235, 0.22)",
        }}
      >
        {t("btn.new_dossier")}
        <svg
          viewBox="0 0 24 24"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-2 w-72 overflow-hidden rounded-xl border shadow-xl"
          style={{
            borderColor: "var(--border-strong)",
            backgroundColor: "var(--bg-panel)",
            boxShadow: "0 16px 40px rgba(10, 20, 40, 0.18)",
          }}
        >
          <p
            className="border-b px-4 py-2.5 text-xs font-medium"
            style={{
              borderColor: "var(--border-default)",
              backgroundColor: "var(--bg-panel)",
              color: "var(--text-muted)",
            }}
          >
            {t("btn.new_dossier_choose")}
          </p>
          <div className="flex flex-col p-1.5" style={{ backgroundColor: "var(--bg-panel)" }}>
            {options.map((opt) => (
              <Link
                key={opt.href}
                href={opt.href}
                role="menuitem"
                onClick={() => setOpen(false)}
                className="ui-new-dossier-option group flex gap-3 rounded-lg px-3 py-3"
              >
                <div
                  className="ui-new-dossier-option__icon flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    color: "var(--accent-from)",
                  }}
                >
                  {opt.icon}
                </div>
                <div className="min-w-0">
                  <span className="block text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                    {opt.label}
                  </span>
                  <span className="mt-0.5 block text-xs leading-snug" style={{ color: "var(--text-muted)" }}>
                    {opt.desc}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
