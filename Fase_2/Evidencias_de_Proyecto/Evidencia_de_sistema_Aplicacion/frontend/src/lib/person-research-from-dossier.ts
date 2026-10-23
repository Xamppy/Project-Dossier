import type { DossierDetailResponse, PersonResearchPayload } from "@/lib/dossier-api";

export type PersonResearchPrefill = {
  replaceDossierId: string | null;
  fullName: string;
  jobArea: string;
  company: string;
  email: string;
  linkedinUrl: string;
  country: string;
  city: string;
  extraKeywords: string;
  researchSource: "pdl" | "gemini_web";
  outputLanguage: string | null;
};

function personFiltersFromDossier(
  dossier: DossierDetailResponse,
): Record<string, unknown> {
  const dd = dossier.dossier_data;
  if (!dd || typeof dd !== "object") return {};
  const pf = (dd as Record<string, unknown>).person_filters;
  return pf && typeof pf === "object" ? (pf as Record<string, unknown>) : {};
}

export function prefillFromDossier(dossier: DossierDetailResponse): PersonResearchPrefill {
  const filters = personFiltersFromDossier(dossier);
  const dd = dossier.dossier_data;
  const root = dd && typeof dd === "object" ? (dd as Record<string, unknown>) : {};

  const rs =
    typeof filters.research_source === "string" ? filters.research_source.trim() : "pdl";

  return {
    replaceDossierId: dossier.id,
    fullName: (
      typeof filters.full_name === "string" ? filters.full_name : dossier.subject_name || ""
    ).trim(),
    jobArea: typeof filters.job_area === "string" ? filters.job_area.trim() : "",
    company: typeof filters.company === "string" ? filters.company.trim() : "",
    email: (
      typeof filters.email === "string" ? filters.email : dossier.subject_email || ""
    ).trim(),
    linkedinUrl:
      typeof filters.linkedin_url === "string" ? filters.linkedin_url.trim() : "",
    country: typeof filters.country === "string" ? filters.country.trim() : "",
    city: typeof filters.city === "string" ? filters.city.trim() : "",
    extraKeywords:
      typeof filters.extra_keywords === "string" ? filters.extra_keywords.trim() : "",
    researchSource: rs === "gemini_web" ? "gemini_web" : "pdl",
    outputLanguage:
      typeof root.output_language === "string" && root.output_language.trim()
        ? root.output_language.trim()
        : null,
  };
}

export function buildPersonResearchHref(dossier: DossierDetailResponse): string {
  const p = prefillFromDossier(dossier);
  const params = new URLSearchParams();
  params.set("replace", dossier.id);
  if (p.fullName) params.set("full_name", p.fullName);
  if (p.jobArea) params.set("job_area", p.jobArea);
  if (p.company) params.set("company", p.company);
  if (p.email) params.set("email", p.email);
  if (p.linkedinUrl) params.set("linkedin_url", p.linkedinUrl);
  if (p.country) params.set("country", p.country);
  if (p.city) params.set("city", p.city);
  if (p.extraKeywords) params.set("extra_keywords", p.extraKeywords);
  if (p.researchSource === "gemini_web") params.set("research_source", "gemini_web");
  return `/dashboard/person-research?${params.toString()}`;
}

export function parsePersonResearchSearchParams(
  searchParams: URLSearchParams,
): Partial<PersonResearchPrefill> {
  const replace = searchParams.get("replace")?.trim() || null;
  const rs = searchParams.get("research_source")?.trim();
  return {
    replaceDossierId: replace,
    fullName: searchParams.get("full_name")?.trim() || "",
    jobArea: searchParams.get("job_area")?.trim() || "",
    company: searchParams.get("company")?.trim() || "",
    email: searchParams.get("email")?.trim() || "",
    linkedinUrl: searchParams.get("linkedin_url")?.trim() || "",
    country: searchParams.get("country")?.trim() || "",
    city: searchParams.get("city")?.trim() || "",
    extraKeywords: searchParams.get("extra_keywords")?.trim() || "",
    researchSource: rs === "gemini_web" ? "gemini_web" : "pdl",
    outputLanguage: null,
  };
}

export function buildPersonResearchPayloadFromDossier(
  dossier: DossierDetailResponse,
  outputLanguage: string,
  options?: { forceRefresh?: boolean; replaceDossierId?: string | null },
): PersonResearchPayload | null {
  const prefill = prefillFromDossier(dossier);
  if (prefill.fullName.length < 2) return null;

  const payload: PersonResearchPayload = {
    full_name: prefill.fullName,
    research_source: prefill.researchSource,
    max_profiles: 1,
    output_language: prefill.outputLanguage || outputLanguage,
    replace_dossier_id: options?.replaceDossierId ?? prefill.replaceDossierId ?? undefined,
  };

  if (prefill.jobArea) payload.job_area = prefill.jobArea;
  if (prefill.company) payload.company = prefill.company;
  if (prefill.email) payload.email = prefill.email;
  if (prefill.linkedinUrl) payload.linkedin_url = prefill.linkedinUrl;
  if (prefill.country) payload.country = prefill.country;
  if (prefill.city) payload.city = prefill.city;
  if (prefill.extraKeywords) payload.extra_keywords = prefill.extraKeywords;
  if (options?.forceRefresh) payload.force_refresh = true;

  return payload;
}
