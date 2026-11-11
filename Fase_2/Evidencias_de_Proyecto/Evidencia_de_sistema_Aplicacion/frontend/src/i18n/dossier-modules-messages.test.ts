import { describe, expect, it } from "vitest";
import { createTranslator } from "@/i18n";
import de from "@/i18n/messages/de";
import en from "@/i18n/messages/en";
import es from "@/i18n/messages/es";
import fr from "@/i18n/messages/fr";
import it_ from "@/i18n/messages/it";
import pt from "@/i18n/messages/pt";
import type { Locale, TranslationKey } from "@/i18n/types";

// S3.7 (CA10): los textos de las secciones por módulo existen en los seis catálogos propios
// con los mismos marcadores. en-gb hereda de en (no hay variante ortográfica que cambiar).

const OWN: Record<string, Record<string, string>> = { es, pt, it: it_, fr, de };
const KEYS = (Object.keys(en) as TranslationKey[]).filter((k) => k.startsWith("dossier_modules."));
const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("i18n · textos de S3.7", () => {
  it("el catálogo inglés trae todas las claves de las secciones", () => {
    expect(KEYS.length).toBeGreaterThanOrEqual(49);
  });

  it.each(Object.keys(OWN))("%s traduce cada clave con los mismos marcadores", (locale) => {
    const messages = OWN[locale];
    const propias = Object.keys(messages).filter((k) => k.startsWith("dossier_modules."));
    expect(propias.sort()).toEqual([...KEYS].sort());
    for (const key of KEYS) {
      const text = messages[key];
      expect(text, `${locale} · ${key}`).toBeTruthy();
      expect(placeholders(text), `${locale} · ${key}`).toEqual(placeholders((en as Record<string, string>)[key]));
    }
  });

  it.each(["es", "en", "en-gb", "pt", "it", "fr", "de"] as Locale[])(
    "%s nunca muestra la clave en lugar del texto",
    (locale) => {
      const t = createTranslator(locale);
      for (const key of KEYS) expect(t(key)).not.toBe(key);
    },
  );
});
