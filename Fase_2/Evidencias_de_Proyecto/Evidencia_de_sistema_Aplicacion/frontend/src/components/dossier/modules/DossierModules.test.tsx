import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { createTranslator } from "@/i18n";
import { parseExecutivePayload, parseModules, readDossierView } from "@/lib/dossier-modules";
import { MENCION, PAYLOAD, REGISTRO } from "@/test/dossier-modules-fixtures";
import { DossierContent } from "./DossierContent";
import { DossierModules } from "./DossierModules";

// S5.5 (secciones por módulo), S3.5 (registros europeos) y S3.6 (prensa).

vi.mock("@/providers/PreferencesProvider", () => {
  const t = createTranslator("es");
  return { useTranslation: () => ({ t, locale: "es" }) };
});

const t = createTranslator("es");
const payload = parseExecutivePayload(PAYLOAD)!;
const ALEMAN = {
  ...REGISTRO,
  record: { ...REGISTRO.record, jurisdiccion: "de", razon_social: "Acme GmbH", identificador_registro: "HRB 1" },
};
const modulos = parseModules({ corporate_records: [REGISTRO, ALEMAN], press_mentions: [MENCION] });
const vacios = parseModules({});

const seccion = (titulo: string) => screen.getByRole("region", { name: titulo });

describe("DossierModules · contrato estructurado (S5.5)", () => {
  it("CA5 · dibuja cada módulo del contrato", () => {
    render(<DossierModules payload={payload} modules={vacios} />);

    expect(within(seccion(t("dossier_modules.summary"))).getByText(PAYLOAD.executive_summary)).toBeTruthy();
    expect(within(seccion(t("dossier_modules.meeting"))).getByText("Revisión trimestral")).toBeTruthy();
    expect(within(seccion(t("dossier_modules.participants"))).getByText("Jane Doe")).toBeTruthy();
    expect(within(seccion(t("dossier_modules.participants"))).getByText("CFO · Acme")).toBeTruthy();

    const carrera = seccion(t("dossier_modules.career"));
    expect(within(carrera).getByText("CFO")).toBeTruthy();
    expect(within(carrera).getByText(t("dossier_modules.current"))).toBeTruthy();

    const riesgos = seccion(t("dossier_modules.risks"));
    expect(within(riesgos).getByText("Litigio abierto")).toBeTruthy();
    expect(within(riesgos).getByText(t("dossier_modules.severity.high"))).toBeTruthy();

    const temas = seccion(t("dossier_modules.starters"));
    expect(within(temas).getByText("Expansión")).toBeTruthy();
    expect(within(temas).getByText("¿Cómo va Lyon?")).toBeTruthy();

    const rec = seccion(t("dossier_modules.recommendation"));
    expect(within(rec).getByText(t("dossier_modules.decision.proceed_with_caution"))).toBeTruthy();
    expect(within(rec).getByText(t("dossier_modules.risk_level.medium"))).toBeTruthy();
    expect(within(rec).getByText("Pedir estados financieros")).toBeTruthy();

    const conf = seccion(t("dossier_modules.confidence"));
    expect(within(conf).getByText("Cargo actual")).toBeTruthy();
    expect(within(conf).queryByText(t("dossier_modules.confidence_medium"))).toBeNull();

    expect(within(seccion(t("dossier_modules.sources"))).getByText("People Data Labs")).toBeTruthy();
  });

  it("CA9 · no muestra las secciones vacías", () => {
    const minimo = parseExecutivePayload({ executive_summary: "Resumen de más de veinte letras.", conversation_starters: [] })!;
    render(<DossierModules payload={minimo} modules={vacios} />);
    expect(screen.getAllByRole("region")).toHaveLength(1);
    expect(screen.queryByRole("region", { name: t("dossier_modules.press") })).toBeNull();
    expect(screen.queryByRole("region", { name: t("dossier_modules.corporate_records") })).toBeNull();
  });
});

describe("Registros europeos (S3.5)", () => {
  it("CA7 · agrupa por país y muestra los datos del registro", () => {
    render(<DossierModules payload={null} modules={modulos} />);
    const registros = seccion(t("dossier_modules.corporate_records"));

    const francia = within(registros).getByRole("group", { name: "Francia" });
    expect(within(francia).getByText("Acme France SAS")).toBeTruthy();
    expect(within(francia).getByText("123456789")).toBeTruthy();
    expect(within(francia).getByText("active")).toBeTruthy();
    expect(within(francia).getByText("SAS")).toBeTruthy();
    expect(within(francia).getByText("Paris, France")).toBeTruthy();
    expect(within(francia).getByText("Marie Curie (Présidente)")).toBeTruthy();

    const alemania = within(registros).getByRole("group", { name: "Alemania" });
    expect(within(alemania).getByText("Acme GmbH")).toBeTruthy();

    const enlace = within(francia).getByRole("link", { name: t("dossier_modules.view_registry") });
    expect(enlace.getAttribute("href")).toBe(REGISTRO.record.url_fuente);
    expect(enlace.getAttribute("target")).toBe("_blank");
    expect(enlace.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("CA9 · un registro con enlace peligroso se muestra sin enlace", () => {
    const malo = parseModules({
      corporate_records: [{ ...REGISTRO, record: { ...REGISTRO.record, url_fuente: "javascript:alert(1)" } }],
    });
    render(<DossierModules payload={null} modules={malo} />);
    expect(screen.getByText("Acme France SAS")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("Prensa (S3.6)", () => {
  it("CA8 · muestra titular, medio, fecha, resumen, proveedor y enlace seguro", () => {
    render(<DossierModules payload={null} modules={modulos} />);
    const prensa = seccion(t("dossier_modules.press"));
    expect(within(prensa).getByText(MENCION.headline)).toBeTruthy();
    expect(within(prensa).getByText(/Le Diario/)).toBeTruthy();
    expect(within(prensa).getByText(/2026/)).toBeTruthy();
    expect(within(prensa).getByText(MENCION.summary)).toBeTruthy();
    expect(within(prensa).getByText(t("dossier_modules.press_via", { provider: "GDELT DOC 2.0" }))).toBeTruthy();
    const enlace = within(prensa).getByRole("link", { name: t("dossier_modules.read_article") });
    expect(enlace.getAttribute("href")).toBe(MENCION.url);
    expect(enlace.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("CA9 · el texto externo nunca se interpreta como HTML", () => {
    const xss = parseModules({
      press_mentions: [{ ...MENCION, headline: '<img src=x onerror="alert(1)">', summary: "<b>negrita</b>", url: "javascript:alert(1)" }],
    });
    const { container } = render(<DossierModules payload={null} modules={xss} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("DossierContent · qué se ve en el detalle", () => {
  const cuerpo = "# Informe completo\n\nTexto del **informe**.";

  it("CA5 · con contrato: secciones y el informe en texto plegado tras un botón", async () => {
    const view = readDossierView({ content_kind: "structured", executive_payload: PAYLOAD, modules: {} });
    render(<DossierContent view={view} body={cuerpo} fallback={null} />);

    expect(screen.getByText(PAYLOAD.executive_summary)).toBeTruthy();
    expect(screen.queryByText("Informe completo")).toBeNull();

    const boton = screen.getByRole("button", { name: t("dossier_modules.show_text") });
    expect(boton.getAttribute("aria-expanded")).toBe("false");
    await userEvent.click(boton);
    expect(screen.getByRole("heading", { name: "Informe completo" })).toBeTruthy();
    expect(screen.getByRole("button", { name: t("dossier_modules.hide_text") }).getAttribute("aria-expanded")).toBe("true");
  });

  it("CA6 · sin contrato: el Markdown de siempre, con registros y prensa encima", () => {
    const view = readDossierView({ content_kind: "legacy_markdown", modules: { corporate_records: [REGISTRO], press_mentions: [MENCION] } });
    render(<DossierContent view={view} body={cuerpo} fallback={null} />);

    const titulo = screen.getByRole("heading", { name: "Informe completo" });
    const registros = seccion(t("dossier_modules.corporate_records"));
    expect(registros.compareDocumentPosition(titulo) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole("button", { name: t("dossier_modules.show_text") })).toBeNull();
  });

  it("CA6 · un histórico sin módulos se ve igual que antes", () => {
    const view = readDossierView({ content_kind: "legacy_markdown", executive_payload: null });
    render(<DossierContent view={view} body={cuerpo} fallback={null} />);
    expect(screen.getByRole("heading", { name: "Informe completo" })).toBeTruthy();
    expect(screen.queryAllByRole("region")).toHaveLength(1);
  });

  it("sin cuerpo de informe muestra el aviso que le pasa el detalle", () => {
    const view = readDossierView({});
    render(<DossierContent view={view} body="" fallback={<p>Sin informe</p>} />);
    expect(screen.getByText("Sin informe")).toBeTruthy();
  });
});
