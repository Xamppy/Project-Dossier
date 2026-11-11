"use client";

import { useEffect, useState } from "react";
import type { TranslationKey } from "@/i18n/types";
import { fetchAdminPlanSettings, patchAdminPlanSetting, type AdminPlanSetting } from "@/lib/dossier-api";
import { useTranslation } from "@/providers/PreferencesProvider";

/**
 * UX-ADMIN-01: tope de dossiers generándose a la vez por usuario, según el plan.
 * Solo se monta en `/dashboard/admin`; el backend exige admin de plataforma.
 */

const PLAN_NAME: Record<AdminPlanSetting["plan"], TranslationKey> = {
  free: "billing.plan_free_name",
  pro: "billing.plan_pro_name",
  enterprise: "billing.plan_enterprise_name",
};

const MIN = 1;
const MAX = 100;

function parseLimit(raw: string): number | null {
  if (!/^\d+$/.test(raw.trim())) return null;
  const n = Number(raw);
  return n >= MIN && n <= MAX ? n : null;
}

export function PlanLimitsPanel() {
  const { t, locale } = useTranslation();
  const [plans, setPlans] = useState<AdminPlanSetting[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "error"; plan: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAdminPlanSettings()
      .then(({ plans: rows }) => {
        if (cancelled) return;
        setPlans(rows);
        setDrafts(Object.fromEntries(rows.map((p) => [p.plan, String(p.max_concurrent_dossiers)])));
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function save(plan: AdminPlanSetting["plan"]) {
    const value = parseLimit(drafts[plan] ?? "");
    if (value === null) return;
    setSaving(plan);
    setFeedback(null);
    try {
      const updated = await patchAdminPlanSetting(plan, value);
      setPlans((prev) => (prev ?? []).map((p) => (p.plan === plan ? updated : p)));
      setDrafts((prev) => ({ ...prev, [plan]: String(updated.max_concurrent_dossiers) }));
      setFeedback({ kind: "ok", plan });
    } catch {
      setFeedback({ kind: "error", plan });
    } finally {
      setSaving(null);
    }
  }

  function lastChange(p: AdminPlanSetting): string {
    if (!p.updated_at || !p.updated_by_email) return t("admin.plan_limits.never");
    let date = p.updated_at;
    try {
      date = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(p.updated_at));
    } catch {
      /* fecha ilegible: se muestra tal cual */
    }
    return t("admin.plan_limits.updated_by", { date, email: p.updated_by_email });
  }

  if (loadError) {
    return (
      <p role="alert" className="px-2 py-3 text-sm" style={{ color: "var(--accent-danger, #f87171)" }}>
        {t("admin.plan_limits.load_error")}
      </p>
    );
  }
  if (!plans) return null;

  return (
    <div className="flex flex-col gap-3 px-2 pt-2">
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        {t("admin.plan_limits.hint")}
      </p>
      <div className="overflow-x-auto rounded-lg border" style={{ borderColor: "var(--border-subtle)" }}>
        <table className="min-w-full text-left text-sm">
          <thead style={{ backgroundColor: "var(--bg-surface-strong)" }}>
            <tr>
              <th className="px-3 py-2 font-medium">{t("admin.plan_limits.col_plan")}</th>
              <th className="px-3 py-2 font-medium">{t("admin.plan_limits.col_max")}</th>
              <th className="px-3 py-2 font-medium">{t("admin.plan_limits.col_updated")}</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {plans.map((p) => {
              const draft = drafts[p.plan] ?? "";
              const value = parseLimit(draft);
              const changed = value !== null && value !== p.max_concurrent_dossiers;
              const name = t(PLAN_NAME[p.plan]);
              const inputId = `plan-limit-${p.plan}`;
              return (
                <tr key={p.plan} aria-label={name} className="border-t" style={{ borderColor: "var(--border-subtle)" }}>
                  <td className="px-3 py-2 font-medium" style={{ color: "var(--text-primary)" }}>
                    <label htmlFor={inputId}>{name}</label>
                  </td>
                  <td className="px-3 py-2">
                    <input
                      id={inputId}
                      type="number"
                      inputMode="numeric"
                      min={MIN}
                      max={MAX}
                      step={1}
                      value={draft}
                      aria-invalid={value === null}
                      onChange={(e) => {
                        setDrafts((prev) => ({ ...prev, [p.plan]: e.target.value }));
                        setFeedback(null);
                      }}
                      className="w-20 rounded-md border px-2 py-1 tabular-nums"
                      style={{ borderColor: "var(--border-default)", backgroundColor: "var(--bg-surface)" }}
                    />
                    {value === null ? (
                      <p className="mt-1 text-xs" style={{ color: "var(--accent-danger, #f87171)" }}>
                        {t("admin.plan_limits.invalid")}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-xs" style={{ color: "var(--text-muted)" }}>
                    {lastChange(p)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      disabled={!changed || saving !== null}
                      onClick={() => void save(p.plan)}
                      className="rounded-lg border px-3 py-1.5 text-xs font-medium disabled:opacity-50"
                      style={{ borderColor: "var(--border-default)", color: "var(--text-primary)" }}
                    >
                      {saving === p.plan ? t("admin.plan_limits.saving") : t("admin.plan_limits.save")}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {feedback?.kind === "ok" ? (
        <p role="status" className="text-sm" style={{ color: "var(--text-secondary)" }}>
          {t("admin.plan_limits.saved")}
        </p>
      ) : null}
      {feedback?.kind === "error" ? (
        <p role="alert" className="text-sm" style={{ color: "var(--accent-danger, #f87171)" }}>
          {t("admin.plan_limits.save_error")}
        </p>
      ) : null}
    </div>
  );
}
