"use client";

import { useEffect, useState } from "react";
import type { TranslationKey } from "@/i18n/types";
import {
  fetchAdminNewsSources,
  patchAdminNewsSource,
  type AdminNewsSource,
  type AdminNewsSourcePatch,
  type NewsSourceDepth,
  type NewsSourcePlan,
} from "@/lib/dossier-api";
import { useTranslation } from "@/providers/PreferencesProvider";

/**
 * UX-ADMIN-02: el admin de plataforma decide cuándo se usa cada fuente de prensa, en qué
 * planes, cuánto cuesta y cuántas consultas diarias admite. Las claves de las APIs viven solo
 * en el servidor: aquí solo se ve si están configuradas.
 */

const PLANES: { id: NewsSourcePlan; label: TranslationKey }[] = [
  { id: "free", label: "billing.plan_free_name" },
  { id: "pro", label: "billing.plan_pro_name" },
  { id: "enterprise", label: "billing.plan_enterprise_name" },
];

const PROFUNDIDADES: { id: NewsSourceDepth; label: TranslationKey }[] = [
  { id: "basic", label: "admin.news.depth_basic" },
  { id: "standard", label: "admin.news.depth_standard" },
  { id: "deep", label: "admin.news.depth_deep" },
];

type Borrador = {
  enabled: boolean;
  use_for_corporate: boolean;
  use_for_person: boolean;
  min_depth: NewsSourceDepth;
  plans: NewsSourcePlan[];
  extra_credits: string;
  max_results: string;
  daily_limit: string;
};

function borradorDe(f: AdminNewsSource): Borrador {
  return {
    enabled: f.enabled,
    use_for_corporate: f.use_for_corporate,
    use_for_person: f.use_for_person,
    min_depth: f.min_depth,
    plans: [...f.plans],
    extra_credits: String(f.extra_credits),
    max_results: String(f.max_results),
    daily_limit: f.daily_limit === null ? "" : String(f.daily_limit),
  };
}

function entero(raw: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(raw.trim())) return null;
  const n = Number(raw);
  return n >= min && n <= max ? n : null;
}

type Validacion = {
  extra: number | null;
  max: number | null;
  /** `undefined` = valor inválido; `null` = sin límite. */
  daily: number | null | undefined;
  planesOk: boolean;
};

function validar(b: Borrador): Validacion {
  const daily = b.daily_limit.trim() === "" ? null : (entero(b.daily_limit, 1, 100000) ?? undefined);
  return {
    extra: entero(b.extra_credits, 0, 20),
    max: entero(b.max_results, 1, 50),
    daily,
    planesOk: b.plans.length > 0,
  };
}

function esValido(v: Validacion): boolean {
  return v.extra !== null && v.max !== null && v.daily !== undefined && v.planesOk;
}

/** Solo lo que cambió respecto de lo guardado. */
function cambios(f: AdminNewsSource, b: Borrador, v: Validacion): AdminNewsSourcePatch {
  const out: AdminNewsSourcePatch = {};
  if (b.enabled !== f.enabled) out.enabled = b.enabled;
  if (b.use_for_corporate !== f.use_for_corporate) out.use_for_corporate = b.use_for_corporate;
  if (b.use_for_person !== f.use_for_person) out.use_for_person = b.use_for_person;
  if (b.min_depth !== f.min_depth) out.min_depth = b.min_depth;
  const planes = PLANES.map((p) => p.id).filter((id) => b.plans.includes(id));
  if (planes.join() !== f.plans.join()) out.plans = planes;
  if (v.extra !== null && v.extra !== f.extra_credits) out.extra_credits = v.extra;
  if (v.max !== null && v.max !== f.max_results) out.max_results = v.max;
  if (v.daily !== undefined && v.daily !== f.daily_limit) out.daily_limit = v.daily;
  return out;
}

const inputClass = "w-full rounded-md border px-2 py-1 text-sm tabular-nums";
const inputStyle = { borderColor: "var(--border-default)", backgroundColor: "var(--bg-surface)" } as const;
const errorStyle = { color: "var(--accent-danger, #f87171)" } as const;
const mutedStyle = { color: "var(--text-muted)" } as const;

export function NewsSourcesPanel() {
  const { t, locale } = useTranslation();
  const [fuentes, setFuentes] = useState<AdminNewsSource[] | null>(null);
  const [borradores, setBorradores] = useState<Record<string, Borrador>>({});
  const [loadError, setLoadError] = useState(false);
  const [guardando, setGuardando] = useState<string | null>(null);
  const [aviso, setAviso] = useState<{ kind: "ok" | "error"; key: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAdminNewsSources()
      .then(({ sources }) => {
        if (cancelled) return;
        setFuentes(sources);
        setBorradores(Object.fromEntries(sources.map((f) => [f.key, borradorDe(f)])));
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function editar(key: string, parcial: Partial<Borrador>) {
    setBorradores((prev) => ({ ...prev, [key]: { ...prev[key], ...parcial } }));
    setAviso(null);
  }

  async function guardar(f: AdminNewsSource) {
    const b = borradores[f.key];
    const v = validar(b);
    const cuerpo = cambios(f, b, v);
    if (!esValido(v) || Object.keys(cuerpo).length === 0) return;
    setGuardando(f.key);
    setAviso(null);
    try {
      const actualizada = await patchAdminNewsSource(f.key, cuerpo);
      setFuentes((prev) => (prev ?? []).map((x) => (x.key === f.key ? actualizada : x)));
      setBorradores((prev) => ({ ...prev, [f.key]: borradorDe(actualizada) }));
      setAviso({ kind: "ok", key: f.key });
    } catch {
      setAviso({ kind: "error", key: f.key });
    } finally {
      setGuardando(null);
    }
  }

  function ultimoCambio(f: AdminNewsSource): string {
    if (!f.updated_at || !f.updated_by_email) return t("admin.news.never");
    let date = f.updated_at;
    try {
      date = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(f.updated_at));
    } catch {
      /* fecha ilegible: se muestra tal cual */
    }
    return t("admin.news.updated_by", { date, email: f.updated_by_email });
  }

  if (loadError) {
    return (
      <p role="alert" className="px-2 py-3 text-sm" style={errorStyle}>
        {t("admin.news.load_error")}
      </p>
    );
  }
  if (!fuentes) return null;

  return (
    <div className="flex flex-col gap-3 px-2 pt-2">
      <p className="text-sm" style={mutedStyle}>
        {t("admin.news.hint")}
      </p>
      {fuentes.length === 0 ? (
        <p className="text-sm" style={mutedStyle}>
          {t("admin.news.empty")}
        </p>
      ) : null}
      {fuentes.map((f) => {
        const b = borradores[f.key] ?? borradorDe(f);
        const v = validar(b);
        const pendiente = Object.keys(cambios(f, b, v)).length > 0;
        const id = (campo: string) => `news-${f.key}-${campo}`;
        const tituloId = id("titulo");
        return (
          <section
            key={f.key}
            aria-labelledby={tituloId}
            className="flex flex-col gap-3 rounded-lg border p-3"
            style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-surface)" }}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 id={tituloId} className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                {f.name}
              </h3>
              <div className="flex flex-wrap gap-2 text-xs">
                <span
                  className="rounded-full border px-2 py-0.5"
                  style={{
                    borderColor: "var(--border-default)",
                    color: f.enabled ? "var(--accent-from)" : "var(--text-muted)",
                  }}
                >
                  {f.enabled ? t("admin.news.status_on") : t("admin.news.status_off")}
                </span>
                <span
                  className="rounded-full border px-2 py-0.5"
                  style={{
                    borderColor: "var(--border-default)",
                    color: f.configured ? "var(--text-secondary)" : "var(--status-warning, #f59e0b)",
                  }}
                >
                  {!f.key_env_var
                    ? t("admin.news.no_key_needed")
                    : f.configured
                      ? t("admin.news.key_ok")
                      : t("admin.news.key_missing", { var: f.key_env_var })}
                </span>
                <span className="rounded-full border px-2 py-0.5 tabular-nums" style={{ borderColor: "var(--border-default)", ...mutedStyle }}>
                  {f.daily_limit === null
                    ? t("admin.news.used_today", { used: f.used_today })
                    : t("admin.news.used_today_limit", { used: f.used_today, limit: f.daily_limit })}
                </span>
              </div>
            </div>
            {f.description ? (
              <p className="text-xs" style={mutedStyle}>
                {f.description}
              </p>
            ) : null}

            <label className="flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-primary)" }}>
              <input type="checkbox" checked={b.enabled} onChange={(e) => editar(f.key, { enabled: e.target.checked })} />
              {t("admin.news.enabled")}
            </label>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <fieldset className="flex flex-col gap-1 text-sm">
                <legend className="mb-1 text-xs font-medium" style={mutedStyle}>
                  {t("admin.news.use_for")}
                </legend>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={b.use_for_corporate}
                    onChange={(e) => editar(f.key, { use_for_corporate: e.target.checked })}
                  />
                  {t("admin.news.use_corporate")}
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={b.use_for_person}
                    onChange={(e) => editar(f.key, { use_for_person: e.target.checked })}
                  />
                  {t("admin.news.use_person")}
                </label>
              </fieldset>

              <fieldset className="flex flex-col gap-1 text-sm">
                <legend className="mb-1 text-xs font-medium" style={mutedStyle}>
                  {t("admin.news.plans")}
                </legend>
                {PLANES.map((p) => (
                  <label key={p.id} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={b.plans.includes(p.id)}
                      onChange={(e) =>
                        editar(f.key, {
                          plans: e.target.checked ? [...b.plans, p.id] : b.plans.filter((x) => x !== p.id),
                        })
                      }
                    />
                    {t(p.label)}
                  </label>
                ))}
                {!v.planesOk ? (
                  <p className="text-xs" style={errorStyle}>
                    {t("admin.news.invalid_plans")}
                  </p>
                ) : null}
              </fieldset>

              <div className="flex flex-col gap-1 text-sm">
                <label htmlFor={id("depth")} className="text-xs font-medium" style={mutedStyle}>
                  {t("admin.news.min_depth")}
                </label>
                <select
                  id={id("depth")}
                  value={b.min_depth}
                  onChange={(e) => editar(f.key, { min_depth: e.target.value as NewsSourceDepth })}
                  className={inputClass}
                  style={inputStyle}
                >
                  {PROFUNDIDADES.map((d) => (
                    <option key={d.id} value={d.id}>
                      {t(d.label)}
                    </option>
                  ))}
                </select>
                <p className="text-xs" style={mutedStyle}>
                  {t("admin.news.min_depth_hint")}
                </p>
              </div>

              <div className="flex flex-col gap-1 text-sm">
                <label htmlFor={id("extra")} className="text-xs font-medium" style={mutedStyle}>
                  {t("admin.news.extra_credits")}
                </label>
                <input
                  id={id("extra")}
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={20}
                  step={1}
                  value={b.extra_credits}
                  aria-invalid={v.extra === null}
                  onChange={(e) => editar(f.key, { extra_credits: e.target.value })}
                  className={inputClass}
                  style={inputStyle}
                />
                <p className="text-xs" style={v.extra === null ? errorStyle : mutedStyle}>
                  {v.extra === null ? t("admin.news.invalid_extra") : t("admin.news.extra_credits_hint")}
                </p>
              </div>

              <div className="flex flex-col gap-1 text-sm">
                <label htmlFor={id("max")} className="text-xs font-medium" style={mutedStyle}>
                  {t("admin.news.max_results")}
                </label>
                <input
                  id={id("max")}
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={50}
                  step={1}
                  value={b.max_results}
                  aria-invalid={v.max === null}
                  onChange={(e) => editar(f.key, { max_results: e.target.value })}
                  className={inputClass}
                  style={inputStyle}
                />
                {v.max === null ? (
                  <p className="text-xs" style={errorStyle}>
                    {t("admin.news.invalid_max")}
                  </p>
                ) : null}
              </div>

              <div className="flex flex-col gap-1 text-sm">
                <label htmlFor={id("daily")} className="text-xs font-medium" style={mutedStyle}>
                  {t("admin.news.daily_limit")}
                </label>
                <input
                  id={id("daily")}
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={100000}
                  step={1}
                  value={b.daily_limit}
                  aria-invalid={v.daily === undefined}
                  onChange={(e) => editar(f.key, { daily_limit: e.target.value })}
                  className={inputClass}
                  style={inputStyle}
                />
                <p className="text-xs" style={v.daily === undefined ? errorStyle : mutedStyle}>
                  {v.daily === undefined ? t("admin.news.invalid_daily") : t("admin.news.daily_limit_hint")}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-2" style={{ borderColor: "var(--border-subtle)" }}>
              <p className="text-xs" style={mutedStyle}>
                {ultimoCambio(f)}
              </p>
              <div className="flex items-center gap-3">
                {aviso?.key === f.key && aviso.kind === "ok" ? (
                  <p role="status" className="text-xs" style={{ color: "var(--text-secondary)" }}>
                    {t("admin.news.saved")}
                  </p>
                ) : null}
                {aviso?.key === f.key && aviso.kind === "error" ? (
                  <p role="alert" className="text-xs" style={errorStyle}>
                    {t("admin.news.save_error")}
                  </p>
                ) : null}
                <button
                  type="button"
                  disabled={!pendiente || !esValido(v) || guardando !== null}
                  onClick={() => void guardar(f)}
                  className="rounded-lg border px-3 py-1.5 text-xs font-medium disabled:opacity-50"
                  style={{ borderColor: "var(--border-default)", color: "var(--text-primary)" }}
                >
                  {guardando === f.key ? t("admin.news.saving") : t("admin.news.save")}
                </button>
              </div>
            </div>
          </section>
        );
      })}
      <p className="text-xs" style={mutedStyle}>
        {t("admin.news.how_to_add")}
      </p>
    </div>
  );
}
