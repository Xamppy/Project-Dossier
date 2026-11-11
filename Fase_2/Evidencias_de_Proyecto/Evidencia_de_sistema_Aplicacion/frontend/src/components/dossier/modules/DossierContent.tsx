"use client";

import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { DossierView } from "@/lib/dossier-modules";
import { useTranslation } from "@/providers/PreferencesProvider";
import { DossierModules } from "./DossierModules";
import { ModuleCard } from "./ModuleCard";

function Markdown({ body }: { body: string }) {
  return (
    <div className="api-md max-w-none text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
    </div>
  );
}

/**
 * Contenido del detalle del dossier (S5.5).
 *
 * - Con contrato estructurado: secciones por módulo y el informe en texto plegado tras un botón.
 * - Sin contrato: registros europeos y prensa (si los hay) y debajo el Markdown de siempre;
 *   `fallback` es lo que se muestra cuando no hay informe (error o vacío).
 */
export function DossierContent({ view, body, fallback }: { view: DossierView; body: string; fallback: ReactNode }) {
  const { t } = useTranslation();
  const [showText, setShowText] = useState(false);
  const hasBody = body.trim().length > 0;

  if (view.kind === "structured") {
    return (
      <div className="flex flex-col gap-6">
        <DossierModules payload={view.payload} modules={view.modules} />
        {hasBody ? (
          <ModuleCard
            title={t("dossier_modules.text_report")}
            action={
              <button
                type="button"
                aria-expanded={showText}
                onClick={() => setShowText((v) => !v)}
                className="rounded-lg border px-3 py-1.5 text-xs font-medium"
                style={{ borderColor: "var(--border-default)", color: "var(--text-primary)" }}
              >
                {showText ? t("dossier_modules.hide_text") : t("dossier_modules.show_text")}
              </button>
            }
          >
            {showText ? <Markdown body={body} /> : null}
          </ModuleCard>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <DossierModules payload={null} modules={view.modules} />
      <ModuleCard title={t("detail.api_report_title")}>{hasBody ? <Markdown body={body} /> : fallback}</ModuleCard>
    </div>
  );
}
