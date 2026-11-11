"use client";

import { useEffect, useState } from "react";
import type { TranslationKey } from "@/i18n/types";
import {
  fetchAdminPlanSettings,
  patchAdminPlanSetting,
  type AdminPlanSetting,
  type AdminPlanSettingPatch,
} from "@/lib/dossier-api";
import { useTranslation } from "@/providers/PreferencesProvider";

/**
 * UX-ADMIN-01: tope de dossiers generándose a la vez por usuario, según el plan.
 * UX-ADMIN-03: créditos al mes de cada plan (se entregan al registrarse o al cambiar de plan).
 * Solo se monta en `/dashboard/admin`; el backend exige admin de plataforma.
 */

const PLAN_NAME: Record<AdminPlanSetting["plan"], TranslationKey> = {
  free: "billing.plan_free_name",
  pro: "billing.plan_pro_name",
  enterprise: "billing.plan_enterprise_name",
};

const MIN = 1;
const MAX = 100;
const MIN_CREDITS = 0;
const MAX_CREDITS = 1_000_000;

type Borrador = { max: string; credits: string };

function parseEntero(raw: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(raw.trim())) return null;
  const n = Number(raw);
  return n >= min && n <= max ? n : null;
}

const parseLimit = (raw: string) => parseEntero(raw, MIN, MAX);
const parseCredits = (raw: string) => parseEntero(raw, MIN_CREDITS, MAX_CREDITS);

function borradorDe(p: AdminPlanSetting): Borrador {
  return { max: String(p.max_concurrent_dossiers), credits: String(p.monthly_credits) };
}

/** Solo lo que cambió y es válido. */
function cambios(p: AdminPlanSetting, b: Borrador): AdminPlanSettingPatch {
  const out: AdminPlanSettingPatch = {};
  const max = parseLimit(b.max);
  const credits = parseCredits(b.credits);
  if (max !== null && max !== p.max_concurrent_dossiers) out.max_concurrent_dossiers = max;
  if (credits !== null && credits !== p.monthly_credits) out.monthly_credits = credits;
  return out;
}

const inputStyle = { borderColor: "var(--border-default)", backgroundColor: "var(--bg-surface)" } as const;
const errorStyle = { color: "var(--accent-danger, #f87171)" } as const;

export function PlanLimitsPanel() {
  const { t, locale } = useTranslation();
  const [plans, setPlans] = useState<AdminPlanSetting[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Borrador>>({});
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "error"; plan: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAdminPlanSettings()
      .then(({ plans: rows }) => {
        if (cancelled) return;
        setPlans(rows);
        setDrafts(Object.fromEntries(rows.map((p) => [p.plan, borradorDe(p)])));
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function editar(plan: string, parcial: Partial<Borrador>) {
    setDrafts((prev) => ({ ...prev, [plan]: { ...prev[plan], ...parcial } }));
    setFeedback(null);
  }

  async function save(p: AdminPlanSetting) {
    const b = drafts[p.plan];
    if (!b || parseLimit(b.max) === null || parseCredits(b.credits) === null) return;
    const body = cambios(p, b);
    if (Object.keys(body).length === 0) return;
    setSaving(p.plan);
    setFeedback(null);
    try {
      const updated = await patchAdminPlanSetting(p.plan, body);
      setPlans((prev) => (prev ?? []).map((x) => (x.plan === p.plan ? updated : x)));
      setDrafts((prev) => ({ ...prev, [p.plan]: borradorDe(updated) }));
      setFeedback({ kind: "ok", plan: p.plan });
    } catch {
      setFeedback({ kind: "error", plan: p.plan });
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
      <p role="alert" className="px-2 py-3 text-sm" style={errorStyle}>
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
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        {t("admin.plan_limits.credits_hint")}
      </p>
      <div className="overflow-x-auto rounded-lg border" style={{ borderColor: "var(--border-subtle)" }}>
        <table className="min-w-full text-left text-sm">
          <thead style={{ backgroundColor: "var(--bg-surface-strong)" }}>
            <tr>
              <th className="px-3 py-2 font-medium">{t("admin.plan_limits.col_plan")}</th>
              <th className="px-3 py-2 font-medium">{t("admin.plan_limits.col_max")}</th>
              <th className="px-3 py-2 font-medium">{t("admin.plan_limits.col_credits")}</th>
              <th className="px-3 py-2 font-medium">{t("admin.plan_limits.col_updated")}</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {plans.map((p) => {
              const b = drafts[p.plan] ?? borradorDe(p);
              const max = parseLimit(b.max);
              const credits = parseCredits(b.credits);
              const valido = max !== null && credits !== null;
              const changed = valido && Object.keys(cambios(p, b)).length > 0;
              const name = t(PLAN_NAME[p.plan]);
              return (
                <tr key={p.plan} aria-label={name} className="border-t" style={{ borderColor: "var(--border-subtle)" }}>
                  <td className="px-3 py-2 font-medium" style={{ color: "var(--text-primary)" }}>
                    {name}
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="number"
                      inputMode="numeric"
                      aria-label={t("admin.plan_limits.col_max")}
                      min={MIN}
                      max={MAX}
                      step={1}
                      value={b.max}
                      aria-invalid={max === null}
                      onChange={(e) => editar(p.plan, { max: e.target.value })}
                      className="w-20 rounded-md border px-2 py-1 tabular-nums"
                      style={inputStyle}
                    />
                    {max === null ? (
                      <p className="mt-1 text-xs" style={errorStyle}>
                        {t("admin.plan_limits.invalid")}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="number"
                      inputMode="numeric"
                      aria-label={t("admin.plan_limits.col_credits")}
                      min={MIN_CREDITS}
                      max={MAX_CREDITS}
                      step={1}
                      value={b.credits}
                      aria-invalid={credits === null}
                      onChange={(e) => editar(p.plan, { credits: e.target.value })}
                      className="w-28 rounded-md border px-2 py-1 tabular-nums"
                      style={inputStyle}
                    />
                    {credits === null ? (
                      <p className="mt-1 text-xs" style={errorStyle}>
                        {t("admin.plan_limits.invalid_credits")}
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
                      onClick={() => void save(p)}
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
        <p role="alert" className="text-sm" style={errorStyle}>
          {t("admin.plan_limits.save_error")}
        </p>
      ) : null}
    </div>
  );
}
