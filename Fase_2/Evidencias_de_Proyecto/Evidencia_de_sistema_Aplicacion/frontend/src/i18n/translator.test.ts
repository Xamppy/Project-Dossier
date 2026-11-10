import { describe, expect, it } from "vitest";
import { createTranslator } from "@/i18n";

describe("createTranslator · parámetros", () => {
  it("reemplaza cada aparición del mismo parámetro, no solo la primera (S6.3)", () => {
    const t = createTranslator("es");
    const texto = t("settings.expiry_fixed", { hours: 6 });
    expect(texto).not.toContain("{hours}");
    expect(texto.match(/6 horas/g)).toHaveLength(2);
  });

  it("un parámetro que no viene queda como está", () => {
    const t = createTranslator("es");
    expect(t("settings.expiry_fixed")).toContain("{hours}");
  });
});
