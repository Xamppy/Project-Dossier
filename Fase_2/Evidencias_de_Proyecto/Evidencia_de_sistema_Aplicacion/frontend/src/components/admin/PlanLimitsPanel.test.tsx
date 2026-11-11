import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createTranslator } from "@/i18n";
import { DossierApiError, type AdminPlanSetting } from "@/lib/dossier-api";
import { PlanLimitsPanel } from "./PlanLimitsPanel";

// UX-ADMIN-01 (CA10): el admin de plataforma ve y cambia el tope de dossiers a la vez por plan.

const api = vi.hoisted(() => ({
  fetchAdminPlanSettings: vi.fn(),
  patchAdminPlanSetting: vi.fn(),
}));

vi.mock("@/lib/dossier-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dossier-api")>();
  return { ...actual, ...api };
});
vi.mock("@/providers/PreferencesProvider", () => {
  const t = createTranslator("es");
  return { useTranslation: () => ({ t, locale: "es" }) };
});

const t = createTranslator("es");

const PLANES: AdminPlanSetting[] = [
  { plan: "free", max_concurrent_dossiers: 1, updated_at: null, updated_by_email: null },
  { plan: "pro", max_concurrent_dossiers: 3, updated_at: "2026-11-11T12:00:00Z", updated_by_email: "ops@alloxentric.com" },
  { plan: "enterprise", max_concurrent_dossiers: 10, updated_at: null, updated_by_email: null },
];

const fila = (plan: string) => screen.getByRole("row", { name: new RegExp(plan, "i") });
const campo = (plan: string) => within(fila(plan)).getByRole("spinbutton");
const guardar = (plan: string) => within(fila(plan)).getByRole("button", { name: t("admin.plan_limits.save") });

beforeEach(() => {
  api.fetchAdminPlanSettings.mockReset().mockResolvedValue({ plans: PLANES });
  api.patchAdminPlanSetting.mockReset();
});

describe("PlanLimitsPanel", () => {
  it("muestra los tres planes con su tope y quién lo cambió", async () => {
    render(<PlanLimitsPanel />);
    expect(await screen.findByRole("row", { name: /free/i })).toBeTruthy();
    expect((campo("free") as HTMLInputElement).value).toBe("1");
    expect((campo("pro") as HTMLInputElement).value).toBe("3");
    expect((campo("enterprise") as HTMLInputElement).value).toBe("10");
    expect(within(fila("pro")).getByText(/ops@alloxentric\.com/)).toBeTruthy();
    expect(screen.getByText(t("admin.plan_limits.hint"))).toBeTruthy();
  });

  it("guardar sin cambios no está disponible", async () => {
    render(<PlanLimitsPanel />);
    await screen.findByRole("row", { name: /pro/i });
    expect((guardar("pro") as HTMLButtonElement).disabled).toBe(true);
  });

  it("cambia el tope de un plan y lo confirma", async () => {
    const user = userEvent.setup();
    api.patchAdminPlanSetting.mockResolvedValue({
      plan: "pro", max_concurrent_dossiers: 5, updated_at: "2026-11-11T13:00:00Z", updated_by_email: "yo@alloxentric.com",
    });
    render(<PlanLimitsPanel />);
    await screen.findByRole("row", { name: /pro/i });

    await user.clear(campo("pro"));
    await user.type(campo("pro"), "5");
    await user.click(guardar("pro"));

    expect(api.patchAdminPlanSetting).toHaveBeenCalledWith("pro", 5);
    expect(await screen.findByRole("status")).toHaveTextContent(t("admin.plan_limits.saved"));
    expect(within(fila("pro")).getByText(/yo@alloxentric\.com/)).toBeTruthy();
    expect((guardar("pro") as HTMLButtonElement).disabled).toBe(true);
  });

  it.each(["0", "101", ""])("un valor fuera de 1–100 (%s) no se puede guardar", async (valor) => {
    const user = userEvent.setup();
    render(<PlanLimitsPanel />);
    await screen.findByRole("row", { name: /free/i });
    await user.clear(campo("free"));
    if (valor) await user.type(campo("free"), valor);
    expect((guardar("free") as HTMLButtonElement).disabled).toBe(true);
    expect(within(fila("free")).getByText(t("admin.plan_limits.invalid"))).toBeTruthy();
    expect(api.patchAdminPlanSetting).not.toHaveBeenCalled();
  });

  it("si guardar falla, lo dice y conserva lo escrito", async () => {
    const user = userEvent.setup();
    api.patchAdminPlanSetting.mockRejectedValue(new DossierApiError(500, "boom"));
    render(<PlanLimitsPanel />);
    await screen.findByRole("row", { name: /enterprise/i });
    await user.clear(campo("enterprise"));
    await user.type(campo("enterprise"), "20");
    await user.click(guardar("enterprise"));
    expect(await screen.findByRole("alert")).toHaveTextContent(t("admin.plan_limits.save_error"));
    expect((campo("enterprise") as HTMLInputElement).value).toBe("20");
  });

  it("si no puede leer los límites, lo dice", async () => {
    api.fetchAdminPlanSettings.mockRejectedValue(new DossierApiError(403, "no"));
    render(<PlanLimitsPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent(t("admin.plan_limits.load_error"));
  });
});
