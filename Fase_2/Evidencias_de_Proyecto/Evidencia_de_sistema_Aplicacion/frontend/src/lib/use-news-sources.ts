"use client";

import { useEffect, useState } from "react";
import { fetchApplicableNewsSources, type ApplicableNewsSources, type NewsSourceDepth } from "@/lib/dossier-api";

const SIN_FUENTES: ApplicableNewsSources = { sources: [], extra_credits: 0 };

/**
 * UX-ADMIN-02: fuentes de prensa que usaría el dossier y su extra máximo de créditos.
 * Si la consulta falla se muestra sin prensa: el servidor igual valida el saldo al generar.
 */
export function useApplicableNewsSources(
  kind: "corporate" | "person",
  depth: NewsSourceDepth = "standard",
): ApplicableNewsSources {
  const [datos, setDatos] = useState<ApplicableNewsSources>(SIN_FUENTES);

  useEffect(() => {
    let cancelled = false;
    fetchApplicableNewsSources(kind, depth)
      .then((r) => {
        if (!cancelled && r && Array.isArray(r.sources)) setDatos(r);
      })
      .catch(() => {
        if (!cancelled) setDatos(SIN_FUENTES);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, depth]);

  return datos;
}

/** «2» o «2 (hasta 1 por prensa)». */
export function creditsLabel(
  t: (key: "generate.credits_with_press", vars: { total: number; extra: number }) => string,
  base: number,
  extra: number,
): string {
  return extra > 0 ? t("generate.credits_with_press", { total: base + extra, extra }) : String(base);
}
