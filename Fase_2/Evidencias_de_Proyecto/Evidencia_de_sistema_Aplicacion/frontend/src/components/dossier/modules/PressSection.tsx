"use client";

import type { PressMentionApi } from "@/lib/dossier-modules";
import { useTranslation } from "@/providers/PreferencesProvider";
import { ExternalLink, ModuleCard, formatDay } from "./ModuleCard";

/** S3.6: menciones de prensa con su medio, fecha, resumen, proveedor y enlace. */
export function PressSection({ mentions }: { mentions: PressMentionApi[] }) {
  const { t, locale } = useTranslation();
  if (mentions.length === 0) return null;
  return (
    <ModuleCard title={t("dossier_modules.press")}>
      <ul className="flex flex-col gap-3">
        {mentions.map((m, i) => {
          const meta = [m.publisher, formatDay(m.published_date, locale)].filter(Boolean).join(" · ");
          return (
            <li key={`${m.headline}-${i}`} className="rounded-lg border p-3" style={{ borderColor: "var(--border-default)" }}>
              <p className="text-sm font-semibold break-words" style={{ color: "var(--text-primary)" }}>
                {m.headline}
              </p>
              {meta ? (
                <p className="mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>
                  {meta}
                </p>
              ) : null}
              {m.summary ? (
                <p className="mt-2 text-sm break-words" style={{ color: "var(--text-secondary)" }}>
                  {m.summary}
                </p>
              ) : null}
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs" style={{ color: "var(--text-muted)" }}>
                {m.source ? <span>{t("dossier_modules.press_via", { provider: m.source.source_name })}</span> : null}
                {m.url ? <ExternalLink href={m.url}>{t("dossier_modules.read_article")}</ExternalLink> : null}
              </div>
            </li>
          );
        })}
      </ul>
    </ModuleCard>
  );
}
