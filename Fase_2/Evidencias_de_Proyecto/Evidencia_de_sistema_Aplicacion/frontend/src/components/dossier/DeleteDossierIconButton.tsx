"use client";

import { useTranslation } from "@/providers/PreferencesProvider";

type Props = {
  disabled?: boolean;
  isDeleting?: boolean;
  onClick: () => void;
  className?: string;
};

export default function DeleteDossierIconButton({
  disabled,
  isDeleting,
  onClick,
  className = "",
}: Props) {
  const { t } = useTranslation();

  return (
    <button
      type="button"
      disabled={disabled || isDeleting}
      onClick={onClick}
      className={`rounded-lg p-2 text-xs font-medium text-[var(--text-muted)] opacity-70 transition-colors hover:bg-red-500/15 hover:text-red-500 hover:opacity-100 disabled:opacity-40 ${className}`}
      title={t("dossiers.delete_aria")}
      aria-label={t("dossiers.delete_aria")}
    >
      {isDeleting ? (
        t("dossiers.deleting")
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
        </svg>
      )}
    </button>
  );
}
