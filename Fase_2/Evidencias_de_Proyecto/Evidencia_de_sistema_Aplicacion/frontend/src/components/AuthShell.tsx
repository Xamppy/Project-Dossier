"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import BrandLogo from "./BrandLogo";
import { useTranslation } from "@/providers/PreferencesProvider";

type AuthShellProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
  /** Formularios largos (p. ej. registro) con más columnas */
  wide?: boolean;
};

export default function AuthShell({
  title,
  subtitle,
  children,
  footer,
  wide = false,
}: AuthShellProps) {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <aside
        className="relative flex flex-col justify-between overflow-hidden p-8 lg:w-1/2 lg:p-12"
        style={{
          backgroundImage:
            "linear-gradient(180deg, var(--bg-sidebar-start) 0%, var(--bg-sidebar-end) 100%)",
          borderRight: "1px solid var(--border-subtle)",
        }}
      >
        <div
          className="absolute -right-32 -top-32 h-96 w-96 rounded-full opacity-20 blur-3xl"
          style={{
            backgroundImage:
              "linear-gradient(135deg, var(--accent-from) 0%, var(--accent-to) 100%)",
          }}
        />
        <Link href="/" className="relative z-10 flex justify-center lg:justify-start">
          <BrandLogo size="lg" />
        </Link>

        <div className="relative z-10 hidden flex-col gap-6 lg:flex">
          <h2
            className="text-3xl font-semibold leading-tight tracking-tight"
            style={{ color: "var(--text-primary)" }}
          >
            {t("auth.shell.title")}
          </h2>
          <p
            className="max-w-md text-base leading-relaxed"
            style={{ color: "var(--text-muted)" }}
          >
            {t("auth.shell.subtitle")}
          </p>
          <ul className="flex flex-col gap-3 text-sm" style={{ color: "var(--text-muted)" }}>
            <li className="flex items-center gap-3">
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: "var(--brand-cyan)" }}
              />
              {t("auth.shell.bullet_speed")}
            </li>
            <li className="flex items-center gap-3">
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: "var(--brand-cyan)" }}
              />
              {t("auth.shell.bullet_coverage")}
            </li>
            <li className="flex items-center gap-3">
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: "var(--brand-cyan)" }}
              />
              {t("auth.shell.bullet_alerts")}
            </li>
          </ul>
        </div>

        <div className="relative z-10 text-xs" style={{ color: "var(--text-subtle)" }}>
          © 2026 Alloxentric · Universidad Tecnologica Metropolitana
        </div>
      </aside>

      <main className="flex flex-1 items-center justify-center p-6 lg:p-12">
        <div className={wide ? "w-full max-w-xl" : "w-full max-w-md"}>
          <div className="mb-8 flex flex-col gap-2">
            <h1
              className="text-3xl font-semibold tracking-tight"
              style={{ color: "var(--text-primary)" }}
            >
              {title}
            </h1>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              {subtitle}
            </p>
          </div>

          {children}

          <div className="mt-8">{footer}</div>
        </div>
      </main>
    </div>
  );
}
