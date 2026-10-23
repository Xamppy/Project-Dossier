"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useAuthMe } from "@/hooks/useAuthMe";
import { normalizePlanTier, planAllowsCorporateDossier } from "@/lib/plans";
import { useTranslation } from "@/providers/PreferencesProvider";

type Props = {
  children: ReactNode;
};

/** Bloquea generación corporativa en plan Free (módulo B). */
export default function CorporatePlanGuard({ children }: Props) {
  const { t } = useTranslation();
  const { user, loading } = useAuthMe();
  const plan = normalizePlanTier(user?.organization_plan);
  const allowed = planAllowsCorporateDossier(plan);

  if (loading) {
    return (
      <p className="p-8 text-sm" style={{ color: "var(--text-muted)" }}>
        {t("common.loading")}
      </p>
    );
  }

  if (!allowed) {
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
            {t("billing.corporate_requires_pro_title")}
          </h2>
          <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
            {t("billing.corporate_requires_pro")}
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/dashboard/person-research"
              className="inline-block rounded-lg px-4 py-2 text-sm font-medium text-white"
              style={{
                backgroundImage:
                  "linear-gradient(135deg, var(--accent-from) 0%, var(--accent-to) 100%)",
              }}
            >
              {t("billing.corporate_go_person")}
            </Link>
            <Link
              href="/dashboard/settings"
              className="inline-block rounded-lg border px-4 py-2 text-sm font-medium"
              style={{
                borderColor: "var(--border-default)",
                color: "var(--text-primary)",
              }}
            >
              {t("billing.upgrade")}
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
