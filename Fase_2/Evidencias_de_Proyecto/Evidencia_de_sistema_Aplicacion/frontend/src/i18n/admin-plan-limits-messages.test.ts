import { describe, expect, it } from "vitest";
import { createTranslator } from "@/i18n";
import de from "@/i18n/messages/de";
import en from "@/i18n/messages/en";
import es from "@/i18n/messages/es";
import fr from "@/i18n/messages/fr";
import it_ from "@/i18n/messages/it";
import pt from "@/i18n/messages/pt";
import type { Locale, TranslationKey } from "@/i18n/types";

// UX-ADMIN-01 (CA10): textos del panel de límites y del error 409 en los siete idiomas.

const OWN: Record<string, Record<string, string>> = { es, pt, it: it_, fr, de };
const KEYS = (Object.keys(en) as TranslationKey[]).filter(
  (k) => k.startsWith("admin.plan_limits.") || k === "admin.section_plan_limits" || k === "errors.concurrent_dossier_limit",
);
const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("i18n · textos de UX-ADMIN-01", () => {
  it("el catálogo inglés trae las 18 claves (15 de UX-ADMIN-01 y 3 de UX-ADMIN-03)", () => {
    expect(KEYS).toHaveLength(18);
  });

  it.each(Object.keys(OWN))("%s traduce cada clave con los mismos marcadores", (locale) => {
    for (const key of KEYS) {
      const text = OWN[locale][key];
      expect(text, `${locale} · ${key}`).toBeTruthy();
      expect(placeholders(text), `${locale} · ${key}`).toEqual(placeholders((en as Record<string, string>)[key]));
    }
  });

  it.each(["es", "en", "en-gb", "pt", "it", "fr", "de"] as Locale[])("%s nunca muestra la clave", (locale) => {
    const t = createTranslator(locale);
    for (const key of KEYS) expect(t(key)).not.toBe(key);
  });
});
