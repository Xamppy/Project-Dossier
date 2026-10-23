"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useAuthMe } from "@/hooks/useAuthMe";
import { useTranslation } from "@/providers/PreferencesProvider";

type Props = {
  children: ReactNode;
};

/** Bloquea la vista para viewers (solo lectura). */
export default function MutatorGuard({ children }: Props) {
  const { t } = useTranslation();
  const { isViewer, loading } = useAuthMe();

  if (loading) {
    return (
      <p className="p-8 text-sm" style={{ color: "var(--text-muted)" }}>
        {t("common.loading")}
      </p>
    );
  }

  if (isViewer) {
    return (
      <div className="mx-auto max-w-lg p-8">
        <div
          className="rounded-xl border px-6 py-8 text-center"
          style={{
            borderColor: "var(--border-default)",
            backgroundColor: "var(--bg-surface)",
          }}
        >
          <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            {t("rbac.viewer_blocked_title")}
          </h2>
          <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
            {t("rbac.viewer_blocked_hint")}
          </p>
          <Link
            href="/dashboard/dossiers"
            className="mt-6 inline-block rounded-lg px-4 py-2 text-sm font-medium text-white"
            style={{
              backgroundImage:
                "linear-gradient(135deg, var(--accent-from) 0%, var(--accent-to) 100%)",
            }}
          >
            {t("rbac.viewer_go_dossiers")}
          </Link>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
