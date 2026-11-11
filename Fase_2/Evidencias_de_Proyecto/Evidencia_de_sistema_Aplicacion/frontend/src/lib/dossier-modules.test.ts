import { describe, expect, it } from "vitest";
import {
  countryName,
  groupRecordsByCountry,
  parseExecutivePayload,
  parseModules,
  readDossierView,
  safeHref,
} from "./dossier-modules";
import { MENCION, PAYLOAD, REGISTRO } from "@/test/dossier-modules-fixtures";

// S5.5: la pantalla vuelve a comprobar la forma de lo que manda la API y nunca se rompe.
describe("safeHref", () => {
  it.each([
    ["https://a.example/x", "https://a.example/x"],
    ["http://a.example", "http://a.example/"],
    ["javascript:alert(1)", null],
    ["JaVaScRiPt:alert(1)", null],
    ["data:text/html,x", null],
    ["/relativa", null],
    ["", null],
    [null, null],
    [42, null],
  ])("%s → %s", (entrada, esperado) => {
    expect(safeHref(entrada)).toBe(esperado);
  });
});

describe("parseModules", () => {
  it("acepta registros y prensa válidos", () => {
    const m = parseModules({ corporate_records: [REGISTRO], press_mentions: [MENCION] });
    expect(m.corporate_records[0].record.razon_social).toBe("Acme France SAS");
    expect(m.press_mentions[0].source?.source_name).toBe("GDELT DOC 2.0");
  });

  it.each([undefined, null, "x", [], { corporate_records: "no", press_mentions: 3 }])(
    "con una forma inesperada (%s) devuelve listas vacías",
    (entrada) => {
      expect(parseModules(entrada)).toEqual({ corporate_records: [], press_mentions: [] });
    },
  );

  it("descarta elementos sin razón social o sin titular y anula enlaces peligrosos", () => {
    const m = parseModules({
      corporate_records: [{ record: { razon_social: "" } }, "x", { ...REGISTRO, record: { ...REGISTRO.record, url_fuente: "javascript:x" } }],
      press_mentions: [{ headline: "  " }, { ...MENCION, url: "javascript:alert(1)" }],
    });
    expect(m.corporate_records).toHaveLength(1);
    expect(m.corporate_records[0].record.url_fuente).toBeNull();
    expect(m.press_mentions).toHaveLength(1);
    expect(m.press_mentions[0].url).toBeNull();
  });
});

describe("parseExecutivePayload", () => {
  it("lee el contrato completo", () => {
    const p = parseExecutivePayload(PAYLOAD);
    expect(p?.meeting_title).toBe("Revisión trimestral");
    expect(p?.participants).toEqual([{ name: "Jane Doe", role: "CFO", company: "Acme" }]);
    expect(p?.final_recommendation?.decision).toBe("proceed_with_caution");
    expect(p?.confidence_assessment?.low_confidence).toEqual(["Fecha de ingreso"]);
  });

  it("sin resumen ejecutivo no hay contrato", () => {
    expect(parseExecutivePayload({ ...PAYLOAD, executive_summary: "" })).toBeNull();
    expect(parseExecutivePayload("x")).toBeNull();
  });

  it("una recomendación con valores desconocidos se omite; una severidad desconocida queda en media", () => {
    const p = parseExecutivePayload({
      ...PAYLOAD,
      final_recommendation: { ...PAYLOAD.final_recommendation, decision: "comprar" },
      risk_alerts: [{ title: "X", severity: "extrema", description: "" }],
    });
    expect(p?.final_recommendation).toBeNull();
    expect(p?.risk_alerts[0].severity).toBe("medium");
  });
});

describe("readDossierView", () => {
  it("structured con contrato válido → secciones", () => {
    const v = readDossierView({ content_kind: "structured", executive_payload: PAYLOAD, modules: {} });
    expect(v.kind).toBe("structured");
  });

  it("legacy, o structured con contrato inválido → Markdown, con sus módulos", () => {
    expect(readDossierView({ content_kind: "legacy_markdown", executive_payload: null, modules: { press_mentions: [MENCION] } })).toEqual({
      kind: "markdown",
      modules: parseModules({ press_mentions: [MENCION] }),
    });
    expect(readDossierView({ content_kind: "structured", executive_payload: {}, modules: undefined }).kind).toBe("markdown");
    expect(readDossierView({}).kind).toBe("markdown");
  });
});

describe("registros por país", () => {
  it("agrupa por jurisdicción en orden de aparición", () => {
    const de = { ...REGISTRO, record: { ...REGISTRO.record, jurisdiccion: "de", razon_social: "Acme GmbH" } };
    const grupos = groupRecordsByCountry(parseModules({ corporate_records: [REGISTRO, de, REGISTRO] }).corporate_records);
    expect(grupos.map((g) => [g.country, g.records.length])).toEqual([
      ["fr", 2],
      ["de", 1],
    ]);
  });

  it("nombra el país en el idioma del usuario", () => {
    expect(countryName("fr", "es")).toBe("Francia");
    expect(countryName("de", "en")).toBe("Germany");
    expect(countryName("uk", "fr")).toBe("Royaume-Uni");
    expect(countryName("zz", "es")).toBe("ZZ");
  });
});
