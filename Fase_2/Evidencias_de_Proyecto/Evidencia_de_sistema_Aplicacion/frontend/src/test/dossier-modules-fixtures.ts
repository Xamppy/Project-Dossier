// Datos de ejemplo de S5.5 (registros europeos, prensa y contrato estructurado).

export const REGISTRO = {
  record: {
    jurisdiccion: "fr",
    fuente: "recherche-entreprises",
    identificador_registro: "123456789",
    razon_social: "Acme France SAS",
    estado: "active",
    forma_juridica: "SAS",
    fecha_constitucion: "2001-04-02",
    domicilio: { localidad: "Paris", pais: "France" },
    directivos: [{ nombre: "Marie Curie", cargo: "Présidente" }],
    url_fuente: "https://annuaire-entreprises.data.gouv.fr/entreprise/123456789",
    consultado_en: "2026-11-11T12:00:00Z",
  },
  source: {
    source_type: "eu_registry",
    source_name: "recherche-entreprises",
    retrieved_at: "2026-11-11T12:00:00Z",
    url: null,
    record_id: "123456789",
  },
};

export const MENCION = {
  headline: "Acme abre oficina en Lyon",
  publisher: "Le Diario",
  published_date: "2026-11-01",
  summary: "La empresa amplía su presencia.",
  url: "https://diario.example/nota",
  source: { source_type: "gdelt_news", source_name: "GDELT DOC 2.0", retrieved_at: "2026-11-11T12:00:00Z" },
};

export const PAYLOAD = {
  schema_version: "2.0.0",
  meeting_context: { title: "Revisión trimestral" },
  executive_summary: "Jane Doe dirige la expansión europea de Acme desde 2024.",
  participants: [{ name: "Jane Doe", role: "CFO", company: "Acme" }],
  career_trajectory: [
    { role_title: "CFO", company_name: "Acme", start_date: "2024", end_date: null, is_current: true },
  ],
  risk_alerts: [{ title: "Litigio abierto", severity: "high", description: "Demanda en curso.", sources: [] }],
  conversation_starters: [
    { topic: "Expansión", rationale: "Anunciada en octubre.", suggested_opener: "¿Cómo va Lyon?" },
  ],
  data_sources_used: [
    { source_type: "pdl", source_name: "People Data Labs", retrieved_at: "2026-11-11T12:00:00Z" },
  ],
  final_recommendation: {
    key_findings: ["Crecimiento sostenido"],
    overall_risk: "medium",
    decision: "proceed_with_caution",
    next_steps: ["Pedir estados financieros"],
  },
  confidence_assessment: {
    high_confidence: ["Cargo actual"],
    medium_confidence: [],
    low_confidence: ["Fecha de ingreso"],
    inferences: [],
  },
};
