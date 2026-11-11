/**
 * Datos por módulo del detalle del dossier (S5.5, S3.5, S3.6).
 *
 * El backend ya valida el contrato (`executive_payload`, S4.4) y arma `modules` (registros
 * corporativos y prensa). Aquí se vuelve a comprobar la forma, sin confiar en ella: un campo
 * inesperado se ignora en vez de romper la pantalla. Ver specs/proposals/S5.5-dossier-por-modulos.md.
 */
import type { DossierDetailResponse } from "@/lib/dossier-api";

export type SourceCitationApi = {
  source_type: string;
  source_name: string;
  url: string | null;
  retrieved_at: string | null;
  record_id: string | null;
};

export type CorporateRecordApi = {
  jurisdiccion: string;
  fuente: string;
  identificador_registro: string;
  razon_social: string;
  estado: string | null;
  forma_juridica: string | null;
  fecha_constitucion: string | null;
  domicilio: { calle?: string | null; localidad?: string | null; region?: string | null; codigo_postal?: string | null; pais?: string | null } | null;
  directivos: { nombre: string; cargo?: string | null }[];
  url_fuente: string | null;
  consultado_en: string | null;
};

export type CorporateRecordCitationApi = { record: CorporateRecordApi; source: SourceCitationApi | null };

export type PressMentionApi = {
  headline: string;
  publisher: string;
  published_date: string | null;
  summary: string;
  url: string | null;
  source: SourceCitationApi | null;
};

export type CareerPositionApi = {
  role_title: string;
  company_name: string;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
};

export type RiskAlertApi = { title: string; severity: "low" | "medium" | "high"; description: string };
export type ConversationStarterApi = { topic: string; rationale: string; suggested_opener: string };
export type ParticipantApi = { name: string; role: string | null; company: string | null };

export type FinalRecommendationApi = {
  key_findings: string[];
  overall_risk: "low" | "medium" | "high" | "critical";
  decision: "proceed" | "proceed_with_caution" | "escalate_legal_review" | "do_not_proceed";
  next_steps: string[];
};

export type ConfidenceAssessmentApi = {
  high_confidence: string[];
  medium_confidence: string[];
  low_confidence: string[];
  inferences: string[];
};

export type ExecutivePayloadApi = {
  meeting_title: string | null;
  executive_summary: string;
  participants: ParticipantApi[];
  career_trajectory: CareerPositionApi[];
  risk_alerts: RiskAlertApi[];
  conversation_starters: ConversationStarterApi[];
  data_sources_used: SourceCitationApi[];
  final_recommendation: FinalRecommendationApi | null;
  confidence_assessment: ConfidenceAssessmentApi | null;
};

export type DossierModulesApi = {
  corporate_records: CorporateRecordCitationApi[];
  press_mentions: PressMentionApi[];
};

export type DossierView =
  | { kind: "structured"; payload: ExecutivePayloadApi; modules: DossierModulesApi }
  | { kind: "markdown"; modules: DossierModulesApi };

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v.trim() : "");
const strOrNull = (v: unknown): string | null => str(v) || null;
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const strings = (v: unknown): string[] => list(v).map(str).filter(Boolean);

function oneOf<T extends string>(v: unknown, allowed: readonly T[]): T | null {
  return typeof v === "string" && (allowed as readonly string[]).includes(v) ? (v as T) : null;
}

/** La URL solo si es `http(s)` con dominio; cualquier otra cosa no se usa como enlace. */
export function safeHref(url: unknown): string | null {
  if (typeof url !== "string") return null;
  try {
    const parsed = new URL(url.trim());
    if ((parsed.protocol === "http:" || parsed.protocol === "https:") && parsed.hostname) return parsed.href;
  } catch {
    /* no es una URL absoluta */
  }
  return null;
}

function parseSource(v: unknown): SourceCitationApi | null {
  if (!isObj(v)) return null;
  const source_type = str(v.source_type);
  if (!source_type) return null;
  return {
    source_type,
    source_name: str(v.source_name) || source_type,
    url: safeHref(v.url),
    retrieved_at: strOrNull(v.retrieved_at),
    record_id: strOrNull(v.record_id),
  };
}

function parseRecord(v: unknown): CorporateRecordCitationApi | null {
  if (!isObj(v) || !isObj(v.record)) return null;
  const r = v.record;
  const razon_social = str(r.razon_social);
  if (!razon_social) return null;
  const dom = isObj(r.domicilio) ? r.domicilio : null;
  return {
    record: {
      jurisdiccion: str(r.jurisdiccion).toLowerCase(),
      fuente: str(r.fuente),
      identificador_registro: str(r.identificador_registro),
      razon_social,
      estado: strOrNull(r.estado),
      forma_juridica: strOrNull(r.forma_juridica),
      fecha_constitucion: strOrNull(r.fecha_constitucion),
      domicilio: dom
        ? {
            calle: strOrNull(dom.calle),
            localidad: strOrNull(dom.localidad),
            region: strOrNull(dom.region),
            codigo_postal: strOrNull(dom.codigo_postal),
            pais: strOrNull(dom.pais),
          }
        : null,
      directivos: list(r.directivos)
        .filter(isObj)
        .map((d) => ({ nombre: str(d.nombre), cargo: strOrNull(d.cargo) }))
        .filter((d) => d.nombre),
      url_fuente: safeHref(r.url_fuente),
      consultado_en: strOrNull(r.consultado_en),
    },
    source: parseSource(v.source),
  };
}

function parsePress(v: unknown): PressMentionApi | null {
  if (!isObj(v)) return null;
  const headline = str(v.headline);
  if (!headline) return null;
  return {
    headline,
    publisher: str(v.publisher),
    published_date: strOrNull(v.published_date),
    summary: str(v.summary),
    url: safeHref(v.url),
    source: parseSource(v.source),
  };
}

export function parseModules(v: unknown): DossierModulesApi {
  const m = isObj(v) ? v : {};
  return {
    corporate_records: list(m.corporate_records).map(parseRecord).filter((x): x is CorporateRecordCitationApi => x !== null),
    press_mentions: list(m.press_mentions).map(parsePress).filter((x): x is PressMentionApi => x !== null),
  };
}

export function parseExecutivePayload(v: unknown): ExecutivePayloadApi | null {
  if (!isObj(v)) return null;
  const executive_summary = str(v.executive_summary);
  if (!executive_summary) return null;
  const meeting = isObj(v.meeting_context) ? v.meeting_context : {};
  const rec = isObj(v.final_recommendation) ? v.final_recommendation : null;
  const overall = rec ? oneOf(rec.overall_risk, ["low", "medium", "high", "critical"] as const) : null;
  const decision = rec
    ? oneOf(rec.decision, ["proceed", "proceed_with_caution", "escalate_legal_review", "do_not_proceed"] as const)
    : null;
  const conf = isObj(v.confidence_assessment) ? v.confidence_assessment : null;
  return {
    meeting_title: strOrNull(meeting.title) ?? strOrNull(meeting.tema),
    executive_summary,
    participants: list(v.participants)
      .filter(isObj)
      .map((p) => ({ name: str(p.name) || str(p.nombre), role: strOrNull(p.role), company: strOrNull(p.company) }))
      .filter((p) => p.name),
    career_trajectory: list(v.career_trajectory)
      .filter(isObj)
      .map((c) => ({
        role_title: str(c.role_title),
        company_name: str(c.company_name),
        start_date: strOrNull(c.start_date),
        end_date: strOrNull(c.end_date),
        is_current: c.is_current === true,
      }))
      .filter((c) => c.role_title || c.company_name),
    risk_alerts: list(v.risk_alerts)
      .filter(isObj)
      .map((a) => ({
        title: str(a.title),
        severity: oneOf(a.severity, ["low", "medium", "high"] as const) ?? "medium",
        description: str(a.description),
      }))
      .filter((a) => a.title),
    conversation_starters: list(v.conversation_starters)
      .filter(isObj)
      .map((c) => ({ topic: str(c.topic), rationale: str(c.rationale), suggested_opener: str(c.suggested_opener) }))
      .filter((c) => c.topic),
    data_sources_used: list(v.data_sources_used).map(parseSource).filter((s): s is SourceCitationApi => s !== null),
    final_recommendation:
      rec && overall && decision
        ? { key_findings: strings(rec.key_findings), overall_risk: overall, decision, next_steps: strings(rec.next_steps) }
        : null,
    confidence_assessment: conf
      ? {
          high_confidence: strings(conf.high_confidence),
          medium_confidence: strings(conf.medium_confidence),
          low_confidence: strings(conf.low_confidence),
          inferences: strings(conf.inferences),
        }
      : null,
  };
}

/** Qué dibujar: secciones del contrato estructurado o el Markdown de siempre. */
export function readDossierView(
  dossier: Pick<DossierDetailResponse, "content_kind" | "executive_payload" | "modules">,
): DossierView {
  const modules = parseModules(dossier.modules);
  const payload = dossier.content_kind === "structured" ? parseExecutivePayload(dossier.executive_payload) : null;
  return payload ? { kind: "structured", payload, modules } : { kind: "markdown", modules };
}

/** Registros agrupados por jurisdicción, en orden de aparición. */
export function groupRecordsByCountry(
  records: CorporateRecordCitationApi[],
): { country: string; records: CorporateRecordCitationApi[] }[] {
  const groups = new Map<string, CorporateRecordCitationApi[]>();
  for (const r of records) {
    const key = r.record.jurisdiccion || "?";
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  return [...groups].map(([country, recs]) => ({ country, records: recs }));
}

// Jurisdicción del registro (ADR 0003) → código de región ISO para `Intl.DisplayNames`.
const REGION: Record<string, string> = { uk: "GB", us: "US", fr: "FR", de: "DE" };

/** Nombre del país en el idioma del usuario; si no se puede, el código en mayúsculas. */
export function countryName(jurisdiction: string, locale: string): string {
  const region = REGION[jurisdiction];
  if (!region) return jurisdiction.toUpperCase();
  try {
    return new Intl.DisplayNames([locale], { type: "region" }).of(region) ?? region;
  } catch {
    return region;
  }
}
