import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createTranslator } from "@/i18n";
import type { DossierDetailResponse } from "@/lib/dossier-api";
import CorporateDossierDetailView from "./CorporateDossierDetailView";

// El aviso amarillo del dossier de persona: solo con PDL y con la causa real.

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/hooks/useAuthMe", () => ({ useAuthMe: () => ({ user: null }) }));
vi.mock("@/providers/DossierJobsProvider", () => ({
  useDossierJobs: () => ({ cancelJob: vi.fn(), getActivePersonJob: () => null, jobs: [] }),
}));
vi.mock("@/providers/PreferencesProvider", () => {
  const t = createTranslator("es");
  return {
    useTranslation: () => ({
      t,
      locale: "es",
      preferences: { locale: "es", timezone: "UTC", outputLanguage: "match", dateFormat: "dd/mm/yyyy" },
    }),
  };
});

const t = createTranslator("es");

function dossier(researchSource: string, profilesCount: number, warnings: string[]): DossierDetailResponse {
  return {
    id: "d-1",
    subject_name: "Ana Prueba",
    status: "complete",
    created_at: "2026-11-24T12:00:00+00:00",
    updated_at: "2026-11-24T12:00:00+00:00",
    dossier_data: {
      format: "markdown",
      body: "## Informe",
      pipeline: "person_research",
      success: true,
      lusha_diagnostics: {
        profiles_count: profilesCount,
        profile_urls: [],
        warnings,
        filters_applied: { research_source: researchSource },
      },
    },
  } as unknown as DossierDetailResponse;
}

const avisos = () => screen.queryAllByRole("status").map((n) => n.textContent);

describe("detalle del dossier de persona · aviso de registros", () => {
  it("«Web pública» no muestra ningún aviso de registros", () => {
    render(<CorporateDossierDetailView dossier={dossier("gemini_web", 0, [])} />);
    expect(avisos()).not.toContain(t("detail.enrichment_no_profiles"));
    expect(screen.queryByText(t("overview.calendar_enrichment_diagnostics"))).toBeNull();
  });

  it("PDL sin coincidencias muestra el aviso de siempre", () => {
    render(<CorporateDossierDetailView dossier={dossier("pdl", 0, [])} />);
    expect(avisos()).toContain(t("detail.enrichment_no_profiles"));
  });

  it("PDL con créditos agotados muestra ese motivo y no que falta información", () => {
    render(
      <CorporateDossierDetailView
        dossier={dossier("pdl", 0, ["PDL (payment_required): You have hit your account maximum"])}
      />,
    );
    expect(avisos()).toContain(t("detail.warn_pdl_credits"));
    expect(avisos()).not.toContain(t("detail.enrichment_no_profiles"));
  });

  it("PDL con perfiles muestra cuántos encontró", () => {
    render(<CorporateDossierDetailView dossier={dossier("pdl", 1, [])} />);
    expect(screen.getByText(t("detail.enrichment_profiles_found", { count: 1 }))).toBeTruthy();
  });
});
