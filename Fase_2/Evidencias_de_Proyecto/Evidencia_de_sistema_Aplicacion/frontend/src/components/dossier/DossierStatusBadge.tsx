"use client";

import { useTranslation } from "@/providers/PreferencesProvider";

type Props = {
  status: string;
  size?: "sm" | "md";
};

function statusStyle(status: string): { bg: string; color: string; labelKey: "dossiers.status_complete" | "dossiers.status_failed" | "dossiers.status_pending" | null } {
  if (status === "complete") {
    return {
      bg: "rgba(34, 197, 94, 0.12)",
      color: "var(--status-success, #22c55e)",
      labelKey: "dossiers.status_complete",
    };
  }
  if (status === "failed") {
    return {
      bg: "rgba(248, 113, 113, 0.12)",
      color: "#f87171",
      labelKey: "dossiers.status_failed",
    };
  }
  if (status === "pending") {
    return {
      bg: "rgba(251, 191, 36, 0.12)",
      color: "var(--status-warning, #fbbf24)",
      labelKey: "dossiers.status_pending",
    };
  }
  return {
    bg: "rgba(251, 191, 36, 0.12)",
    color: "var(--status-warning, #fbbf24)",
    labelKey: null,
  };
}

export default function DossierStatusBadge({ status, size = "sm" }: Props) {
  const { t } = useTranslation();
  const style = statusStyle(status);
  const label = style.labelKey ? t(style.labelKey) : status.replace(/_/g, " ");

  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full font-medium capitalize ${
        size === "md" ? "px-2.5 py-1 text-xs" : "px-2 py-0.5 text-[11px]"
      }`}
      style={{ backgroundColor: style.bg, color: style.color }}
    >
      {label}
    </span>
  );
}
