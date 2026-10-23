import de from "@/i18n/messages/de";
import en from "@/i18n/messages/en";
import enGb from "@/i18n/messages/en-gb";
import es from "@/i18n/messages/es";
import fr from "@/i18n/messages/fr";
import it from "@/i18n/messages/it";
import pt from "@/i18n/messages/pt";
import type { Locale, TranslationKey } from "@/i18n/types";
import { normalizeAppLocale } from "@/i18n/types";

const localeModules: Record<Locale, Record<string, string>> = {
  en: en as Record<string, string>,
  "en-gb": enGb as Record<string, string>,
  es: es as Record<string, string>,
  pt: pt as Record<string, string>,
  it: it as Record<string, string>,
  fr: fr as Record<string, string>,
  de: de as Record<string, string>,
};

/** Diccionario completo por idioma (inglés + sobreescrituras del locale). */
const mergedDictionaries: Record<Locale, Record<string, string>> = {
  en: { ...localeModules.en },
  "en-gb": { ...localeModules.en, ...localeModules["en-gb"] },
  es: { ...localeModules.en, ...localeModules.es },
  pt: { ...localeModules.en, ...localeModules.pt },
  it: { ...localeModules.en, ...localeModules.it },
  fr: { ...localeModules.en, ...localeModules.fr },
  de: { ...localeModules.en, ...localeModules.de },
};

export function createTranslator(locale: Locale) {
  const normalized = normalizeAppLocale(locale);
  const dict = mergedDictionaries[normalized] ?? mergedDictionaries.en;
  const fallback = mergedDictionaries.en;

  return function t(
    key: TranslationKey,
    params?: Record<string, string | number>
  ): string {
    let text = dict[key] ?? fallback[key] ?? key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        text = text.replace(`{${k}}`, String(v));
      }
    }
    return text;
  };
}

export type TranslateFn = ReturnType<typeof createTranslator>;
