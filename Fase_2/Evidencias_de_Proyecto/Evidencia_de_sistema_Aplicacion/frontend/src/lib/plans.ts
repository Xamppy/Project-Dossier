import type { DossierDepth } from "@/lib/dossier-depth";
import type { TranslationKey } from "@/i18n/types";

export type PlanTier = "free" | "pro" | "enterprise";

export const ALLOWED_DEPTHS_BY_PLAN: Record<PlanTier, DossierDepth[]> = {
  free: ["basic"],
  pro: ["basic", "standard", "deep"],
  enterprise: ["basic", "standard", "deep"],
};

export function normalizePlanTier(raw: string | undefined | null): PlanTier {
  const p = (raw || "free").trim().toLowerCase();
  if (p === "pro" || p === "enterprise") return p;
  return "free";
}

export function allowedDepthsForPlan(plan: PlanTier): DossierDepth[] {
  return ALLOWED_DEPTHS_BY_PLAN[plan];
}

export function defaultDepthForPlan(plan: PlanTier): DossierDepth {
  return plan === "free" ? "basic" : "standard";
}

export function planAllowsCorporateDossier(plan: PlanTier): boolean {
  return plan !== "free";
}

export function planAllowsAutomation(plan: PlanTier): boolean {
  return plan !== "free";
}

type TranslateFn = (
  key: TranslationKey,
  params?: Record<string, string | number>,
) => string;

export function planTierLabel(t: TranslateFn, plan: PlanTier): string {
  return t(
    plan === "free"
      ? "billing.plan_free_name"
      : plan === "pro"
        ? "billing.plan_pro_name"
        : "billing.plan_enterprise_name",
  );
}

export function planSummaryLabel(
  t: TranslateFn,
  plan: PlanTier,
  creditsBalance?: number,
  monthlyLimit?: number,
): string {
  const name = planTierLabel(t, plan);
  const cap =
    plan === "enterprise" || (monthlyLimit ?? 0) >= 999_999
      ? t("billing.unlimited")
      : t("billing.plan_cap_short", { limit: monthlyLimit ?? "—" });
  const balance =
    typeof creditsBalance === "number"
      ? t("billing.plan_balance_suffix", { balance: creditsBalance })
      : "";
  return `${name} · ${cap}${balance}`;
}

export type Plan = {
  id: PlanTier;
  name: string;
};

export const PLANS: Plan[] = [
  { id: "free", name: "Free" },
  { id: "pro", name: "Pro" },
  { id: "enterprise", name: "Enterprise" },
];
