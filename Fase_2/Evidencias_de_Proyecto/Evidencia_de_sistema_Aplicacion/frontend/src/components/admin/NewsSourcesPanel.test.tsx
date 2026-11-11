import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createTranslator } from "@/i18n";
import type { AdminNewsSource } from "@/lib/dossier-api";
import { NewsSourcesPanel } from "./NewsSourcesPanel";

// UX-ADMIN-02: el admin de plataforma decide cuándo usar cada fuente de prensa y cuánto cuesta.

const api = vi.hoisted(() => ({
  fetchAdminNewsSources: vi.fn(),
  patchAdminNewsSource: vi.fn(),
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

const base: AdminNewsSource = {
  key: "gdelt_news",
  name: "GDELT DOC 2.0",
  description: "Prensa mundial de los últimos 30 días.",
  configured: true,
  key_env_var: null,
  default_enabled: true,
  enabled: true,
  use_for_corporate: true,
  use_for_person: true,
  min_depth: "basic",
  plans: ["free", "pro", "enterprise"],
  extra_credits: 0,
  max_results: 10,
  daily_limit: null,
  used_today: 4,
  updated_at: null,
  updated_by_email: null,
};

const FUENTES: AdminNewsSource[] = [
  base,
  {
    ...base,
    key: "news_api",
    name: "NewsAPI",
    configured: false,
    key_env_var: "NEWS_API_KEY",
    daily_limit: 100,
    used_today: 7,
    updated_at: "2026-11-11T12:00:00Z",
    updated_by_email: "ops@alloxentric.com",
  },
];

const tarjeta = (nombre: string) => screen.getByRole("region", { name: nombre });
const guardar = (nombre: string) => within(tarjeta(nombre)).getByRole("button", { name: t("admin.news.save") });
const campo = (nombre: string, etiqueta: string) => within(tarjeta(nombre)).getByLabelText(etiqueta);

beforeEach(() => {
  api.fetchAdminNewsSources.mockReset().mockResolvedValue({ sources: FUENTES });
  api.patchAdminNewsSource.mockReset();
});

describe("NewsSourcesPanel", () => {
  it("muestra cada fuente con su estado, la clave que falta y el uso de hoy", async () => {
    render(<NewsSourcesPanel />);
    const gdelt = await screen.findByRole("region", { name: "GDELT DOC 2.0" });
    expect(within(gdelt).getByText(t("admin.news.no_key_needed"))).toBeInTheDocument();
    expect(within(gdelt).getByText(t("admin.news.used_today", { used: 4 }))).toBeInTheDocument();

    const newsapi = tarjeta("NewsAPI");
    expect(within(newsapi).getByText(t("admin.news.key_missing", { var: "NEWS_API_KEY" }))).toBeInTheDocument();
    expect(within(newsapi).getByText(t("admin.news.used_today_limit", { used: 7, limit: 100 }))).toBeInTheDocument();
    expect(within(newsapi).getByText(/ops@alloxentric\.com/)).toBeInTheDocument();
    // Sin cambios no se puede guardar.
    expect(guardar("NewsAPI")).toBeDisabled();
  });

  it("guarda solo lo que cambió", async () => {
    const user = userEvent.setup();
    api.patchAdminNewsSource.mockResolvedValue({ ...base, extra_credits: 2, use_for_person: false });
    render(<NewsSourcesPanel />);
    await screen.findByRole("region", { name: "GDELT DOC 2.0" });

    const extra = campo("GDELT DOC 2.0", t("admin.news.extra_credits"));
    await user.clear(extra);
    await user.type(extra, "2");
    await user.click(campo("GDELT DOC 2.0", t("admin.news.use_person")));
    await user.click(guardar("GDELT DOC 2.0"));

    expect(api.patchAdminNewsSource).toHaveBeenCalledWith("gdelt_news", { extra_credits: 2, use_for_person: false });
    expect(await screen.findByRole("status")).toHaveTextContent(t("admin.news.saved"));
  });

  it("vaciar el límite diario lo quita (null)", async () => {
    const user = userEvent.setup();
    api.patchAdminNewsSource.mockResolvedValue({ ...FUENTES[1], daily_limit: null });
    render(<NewsSourcesPanel />);
    await screen.findByRole("region", { name: "NewsAPI" });

    await user.clear(campo("NewsAPI", t("admin.news.daily_limit")));
    await user.click(guardar("NewsAPI"));
    expect(api.patchAdminNewsSource).toHaveBeenCalledWith("news_api", { daily_limit: null });
  });

  it("cambia profundidad mínima y planes", async () => {
    const user = userEvent.setup();
    api.patchAdminNewsSource.mockResolvedValue(base);
    render(<NewsSourcesPanel />);
    await screen.findByRole("region", { name: "GDELT DOC 2.0" });

    await user.selectOptions(campo("GDELT DOC 2.0", t("admin.news.min_depth")), "deep");
    await user.click(campo("GDELT DOC 2.0", t("billing.plan_free_name")));
    await user.click(guardar("GDELT DOC 2.0"));
    expect(api.patchAdminNewsSource).toHaveBeenCalledWith("gdelt_news", {
      min_depth: "deep",
      plans: ["pro", "enterprise"],
    });
  });

  it("no deja guardar valores fuera de rango ni sin planes", async () => {
    const user = userEvent.setup();
    render(<NewsSourcesPanel />);
    await screen.findByRole("region", { name: "GDELT DOC 2.0" });

    const extra = campo("GDELT DOC 2.0", t("admin.news.extra_credits"));
    await user.clear(extra);
    await user.type(extra, "25");
    expect(within(tarjeta("GDELT DOC 2.0")).getByText(t("admin.news.invalid_extra"))).toBeInTheDocument();
    expect(guardar("GDELT DOC 2.0")).toBeDisabled();

    await user.clear(extra);
    await user.type(extra, "1");
    for (const plan of ["billing.plan_free_name", "billing.plan_pro_name", "billing.plan_enterprise_name"] as const) {
      await user.click(campo("GDELT DOC 2.0", t(plan)));
    }
    expect(within(tarjeta("GDELT DOC 2.0")).getByText(t("admin.news.invalid_plans"))).toBeInTheDocument();
    expect(guardar("GDELT DOC 2.0")).toBeDisabled();
  });

  it("avisa si no puede cargar o guardar", async () => {
    const user = userEvent.setup();
    api.patchAdminNewsSource.mockRejectedValue(new Error("500"));
    render(<NewsSourcesPanel />);
    await screen.findByRole("region", { name: "GDELT DOC 2.0" });
    await user.click(campo("GDELT DOC 2.0", t("admin.news.enabled")));
    await user.click(guardar("GDELT DOC 2.0"));
    expect(await screen.findByRole("alert")).toHaveTextContent(t("admin.news.save_error"));
  });

  it("muestra un error si no hay datos", async () => {
    api.fetchAdminNewsSources.mockRejectedValue(new Error("403"));
    render(<NewsSourcesPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent(t("admin.news.load_error"));
  });
});
