"use client";

import {
  dossierOutputLanguageLabelKey,
  readDossierOutputLanguageCode,
} from "@/lib/dossier-output-language";
import { useTranslation } from "@/providers/PreferencesProvider";

type Props = {
  dossier_data?: unknown;
};

export default function DossierOutputLanguageBadge({ dossier_data }: Props) {
  const { t } = useTranslation();
  const code = readDossierOutputLanguageCode(dossier_data);
  if (!code) return null;

  const language = t(dossierOutputLanguageLabelKey(code));

  return (
    <span
      className="rounded-full border px-3 py-0.5 text-xs font-semibold uppercase tracking-wide"
      style={{
        borderColor: "var(--border-default)",
        color: "var(--text-secondary)",
        backgroundColor: "var(--surface-elevated, transparent)",
      }}
      title={t("detail.output_language_badge", { language })}
    >
      {t("detail.output_language_badge", { language })}
    </span>
  );
}
