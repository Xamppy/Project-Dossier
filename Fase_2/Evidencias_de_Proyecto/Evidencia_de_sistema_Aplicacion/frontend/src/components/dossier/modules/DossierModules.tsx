"use client";

import type { ReactNode } from "react";
import type { TranslationKey } from "@/i18n/types";
import type { DossierModulesApi, ExecutivePayloadApi } from "@/lib/dossier-modules";
import { useTranslation } from "@/providers/PreferencesProvider";
import { CorporateRecordsSection } from "./CorporateRecordsSection";
import { ExternalLink, ModuleCard } from "./ModuleCard";
import { PressSection } from "./PressSection";

/**
 * S5.5: el dossier dibujado desde JSON, un componente por módulo. Sin contrato (`payload`
 * nulo) solo se dibujan los registros corporativos y la prensa. Una sección vacía no aparece.
 */
export function DossierModules({
  payload,
  modules,
}: {
  payload: ExecutivePayloadApi | null;
  modules: DossierModulesApi;
}) {
  return (
    <div className="flex flex-col gap-6">
      {payload ? <SummarySections payload={payload} /> : null}
      <CorporateRecordsSection records={modules.corporate_records} />
      {payload ? <CareerSection payload={payload} /> : null}
      <PressSection mentions={modules.press_mentions} />
      {payload ? <AnalysisSections payload={payload} /> : null}
    </div>
  );
}

const text = { color: "var(--text-secondary)" } as const;
const muted = { color: "var(--text-muted)" } as const;

function Pill({ children }: { children: ReactNode }) {
  return (
    <span
      className="inline-block rounded-full border px-2 py-0.5 text-xs font-medium"
      style={{ borderColor: "var(--border-default)", color: "var(--text-primary)" }}
    >
      {children}
    </span>
  );
}

function SummarySections({ payload }: { payload: ExecutivePayloadApi }) {
  const { t } = useTranslation();
  return (
    <>
      <ModuleCard title={t("dossier_modules.summary")}>
        <p className="whitespace-pre-line text-sm leading-relaxed break-words" style={text}>
          {payload.executive_summary}
        </p>
      </ModuleCard>
      {payload.meeting_title ? (
        <ModuleCard title={t("dossier_modules.meeting")}>
          <p className="text-sm break-words" style={text}>
            {payload.meeting_title}
          </p>
        </ModuleCard>
      ) : null}
      {payload.participants.length > 0 ? (
        <ModuleCard title={t("dossier_modules.participants")}>
          <ul className="flex flex-col gap-2 text-sm">
            {payload.participants.map((p, i) => {
              const detail = [p.role, p.company].filter(Boolean).join(" · ");
              return (
                <li key={`${p.name}-${i}`}>
                  <p className="font-medium break-words" style={{ color: "var(--text-primary)" }}>
                    {p.name}
                  </p>
                  {detail ? (
                    <p className="text-xs" style={muted}>
                      {detail}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </ModuleCard>
      ) : null}
    </>
  );
}

function CareerSection({ payload }: { payload: ExecutivePayloadApi }) {
  const { t } = useTranslation();
  if (payload.career_trajectory.length === 0) return null;
  return (
    <ModuleCard title={t("dossier_modules.career")}>
      <ol className="flex flex-col gap-2 text-sm">
        {payload.career_trajectory.map((c, i) => {
          const end = c.is_current ? t("dossier_modules.present") : c.end_date;
          const period = [c.start_date, end].filter(Boolean).join(" – ");
          return (
            <li key={`${c.role_title}-${c.company_name}-${i}`} className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-medium" style={{ color: "var(--text-primary)" }}>
                {c.role_title}
              </span>
              {c.company_name ? <span style={text}>{c.company_name}</span> : null}
              {period ? (
                <span className="text-xs" style={muted}>
                  {period}
                </span>
              ) : null}
              {c.is_current ? <Pill>{t("dossier_modules.current")}</Pill> : null}
            </li>
          );
        })}
      </ol>
    </ModuleCard>
  );
}

function BulletList({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm" style={text}>
      {items.map((item, i) => (
        <li key={i} className="break-words">
          {item}
        </li>
      ))}
    </ul>
  );
}

function AnalysisSections({ payload }: { payload: ExecutivePayloadApi }) {
  const { t } = useTranslation();
  const rec = payload.final_recommendation;
  const conf = payload.confidence_assessment;
  const confRows: [TranslationKey, string[]][] = conf
    ? [
        ["dossier_modules.confidence_high", conf.high_confidence],
        ["dossier_modules.confidence_medium", conf.medium_confidence],
        ["dossier_modules.confidence_low", conf.low_confidence],
        ["dossier_modules.inferences", conf.inferences],
      ]
    : [];
  const confFilled = confRows.filter(([, items]) => items.length > 0);
  return (
    <>
      {payload.risk_alerts.length > 0 ? (
        <ModuleCard title={t("dossier_modules.risks")}>
          <ul className="flex flex-col gap-3">
            {payload.risk_alerts.map((a, i) => (
              <li key={`${a.title}-${i}`} className="rounded-lg border p-3" style={{ borderColor: "var(--border-default)" }}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                    {a.title}
                  </span>
                  <Pill>{t(`dossier_modules.severity.${a.severity}`)}</Pill>
                </div>
                {a.description ? (
                  <p className="mt-1 text-sm break-words" style={text}>
                    {a.description}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </ModuleCard>
      ) : null}

      {payload.conversation_starters.length > 0 ? (
        <ModuleCard title={t("dossier_modules.starters")}>
          <ul className="flex flex-col gap-3 text-sm">
            {payload.conversation_starters.map((c, i) => (
              <li key={`${c.topic}-${i}`}>
                <p className="font-semibold" style={{ color: "var(--text-primary)" }}>
                  {c.topic}
                </p>
                {c.rationale ? (
                  <p className="mt-0.5 break-words" style={text}>
                    <span style={muted}>{t("dossier_modules.rationale")}: </span>
                    {c.rationale}
                  </p>
                ) : null}
                {c.suggested_opener ? (
                  <p className="mt-0.5 break-words" style={text}>
                    <span style={muted}>{t("dossier_modules.opener")}: </span>
                    <q>{c.suggested_opener}</q>
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </ModuleCard>
      ) : null}

      {rec ? (
        <ModuleCard title={t("dossier_modules.recommendation")}>
          <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <div>
              <dt className="text-xs" style={muted}>
                {t("dossier_modules.decision")}
              </dt>
              <dd>
                <Pill>{t(`dossier_modules.decision.${rec.decision}`)}</Pill>
              </dd>
            </div>
            <div>
              <dt className="text-xs" style={muted}>
                {t("dossier_modules.overall_risk")}
              </dt>
              <dd>
                <Pill>{t(`dossier_modules.risk_level.${rec.overall_risk}`)}</Pill>
              </dd>
            </div>
          </dl>
          {rec.key_findings.length > 0 ? (
            <div className="mt-4">
              <h4 className="mb-1 text-xs font-semibold" style={muted}>
                {t("dossier_modules.key_findings")}
              </h4>
              <BulletList items={rec.key_findings} />
            </div>
          ) : null}
          {rec.next_steps.length > 0 ? (
            <div className="mt-4">
              <h4 className="mb-1 text-xs font-semibold" style={muted}>
                {t("dossier_modules.next_steps")}
              </h4>
              <BulletList items={rec.next_steps} />
            </div>
          ) : null}
        </ModuleCard>
      ) : null}

      {confFilled.length > 0 ? (
        <ModuleCard title={t("dossier_modules.confidence")}>
          <div className="flex flex-col gap-3">
            {confFilled.map(([key, items]) => (
              <div key={key}>
                <h4 className="mb-1 text-xs font-semibold" style={muted}>
                  {t(key)}
                </h4>
                <BulletList items={items} />
              </div>
            ))}
          </div>
        </ModuleCard>
      ) : null}

      {payload.data_sources_used.length > 0 ? (
        <ModuleCard title={t("dossier_modules.sources")}>
          <ul className="flex flex-wrap gap-2">
            {payload.data_sources_used.map((s, i) => (
              <li key={`${s.source_type}-${i}`}>
                {s.url ? <ExternalLink href={s.url}>{s.source_name}</ExternalLink> : <Pill>{s.source_name}</Pill>}
              </li>
            ))}
          </ul>
        </ModuleCard>
      ) : null}
    </>
  );
}
