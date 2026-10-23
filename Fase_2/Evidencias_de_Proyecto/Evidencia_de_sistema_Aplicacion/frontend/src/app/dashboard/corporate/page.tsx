"use client";

import CorporateDossierGenerateView from "@/components/dashboard/CorporateDossierGenerateView";
import CorporatePlanGuard from "@/components/auth/CorporatePlanGuard";
import MutatorGuard from "@/components/auth/MutatorGuard";

/**
 * Generación dedicada de dossiers corporativos (UK Companies House + US SEC).
 */
export default function CorporateDossierGeneratePage() {
  return (
    <MutatorGuard>
      <CorporatePlanGuard>
        <CorporateDossierGenerateView
        initialQuery=""
        autoDisambiguate={false}
        backHref="/dashboard"
        backLabelKey="corporate_page.back"
        titleKey="corporate_page.title"
        subtitleKey="corporate_page.subtitle"
        />
      </CorporatePlanGuard>
    </MutatorGuard>
  );
}
