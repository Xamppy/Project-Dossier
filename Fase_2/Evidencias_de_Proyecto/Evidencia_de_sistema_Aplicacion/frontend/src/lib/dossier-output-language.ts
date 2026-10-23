import type { DossierOutputLanguageCode, TranslationKey } from "@/i18n/types";
import { DOSSIER_OUTPUT_LANGUAGE_CODES } from "@/i18n/types";

const OUTPUT_LANGUAGE_KEYS: Record<DossierOutputLanguageCode, TranslationKey> = {
  es: "locale.es",
  en: "locale.en",
  pt: "locale.pt",
  it: "locale.it",
  fr: "locale.fr",
  de: "locale.de",
};

export function readDossierOutputLanguageCode(dossierData: unknown): DossierOutputLanguageCode | null {
  if (!dossierData || typeof dossierData !== "object" || Array.isArray(dossierData)) {
    return null;
  }
  const raw = (dossierData as Record<string, unknown>).output_language;
  if (typeof raw !== "string" || !raw.trim()) return null;
  const code = raw.trim().toLowerCase().slice(0, 2);
  if (code === "en") return "en";
  if ((DOSSIER_OUTPUT_LANGUAGE_CODES as readonly string[]).includes(code)) {
    return code as DossierOutputLanguageCode;
  }
  return null;
}

export function dossierOutputLanguageLabelKey(
  code: DossierOutputLanguageCode,
): TranslationKey {
  return OUTPUT_LANGUAGE_KEYS[code];
}
