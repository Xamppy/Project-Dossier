import { describe, expect, it } from "vitest";
import { parseSettingsSection } from "@/components/settings/SettingsNav";
import { DEPTH_OPTIONS } from "@/lib/dossier-depth";

// Defectos del informe de pruebas beta (2026-10-06).

describe("informe beta · accesos directos a Configuración", () => {
  it("reconoce la sección pedida en la URL", () => {
    expect(parseSettingsSection("addressbook")).toBe("addressbook");
    expect(parseSettingsSection("notifications")).toBe("notifications");
  });

  it.each([null, undefined, "", "admin", "ADDRESSBOOK"])("ignora %s", (valor) => {
    expect(parseSettingsSection(valor)).toBeNull();
  });
});

describe("informe beta · tiempo estimado de Empresas", () => {
  it("no promete menos de lo medido (hasta ~1 minuto, mismo pipeline en las tres profundidades)", () => {
    const etas = DEPTH_OPTIONS.map((d) => d.etaSeconds);
    expect(Math.min(...etas)).toBeGreaterThanOrEqual(45);
    expect(Math.max(...etas)).toBeLessThanOrEqual(60);
  });
});
