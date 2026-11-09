import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createTranslator } from "@/i18n";
import { getApiBaseUrl } from "@/lib/dossier-api";
import LoginPage from "./page";

const t = createTranslator("es");

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/lib/dossier-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dossier-api")>();
  return { ...actual, getStoredAccessToken: () => null };
});
vi.mock("@/providers/PreferencesProvider", () => ({
  useTranslation: () => ({ t: createTranslator("es"), locale: "es" }),
}));

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("/login · proveedores externos", () => {
  it("Google lleva al inicio de sesión de la API", () => {
    render(<LoginPage />);
    expect(screen.getByRole("link", { name: "Google" })).toHaveAttribute(
      "href",
      `${getApiBaseUrl()}/auth/google/login`,
    );
  });

  it("Microsoft aparece deshabilitado", () => {
    render(<LoginPage />);
    const boton = screen.getByRole("button", { name: "Microsoft" });
    expect(boton).toBeDisabled();
    expect(boton).toHaveAttribute("title", t("auth.login.microsoft_soon"));
  });

  it("muestra el error cuando Google devuelve al login", async () => {
    window.history.replaceState(null, "", "/login?error=google");
    render(<LoginPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(t("auth.error.google"));
  });
});

describe("/login · límite de solicitudes (S5.8)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("explica cuánto esperar en vez de mostrar el código del error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({ detail: { code: "rate_limited", message: "x", retry_after: 37 } }),
            { status: 429, headers: { "Content-Type": "application/json", "Retry-After": "37" } },
          ),
        ),
      ),
    );
    render(<LoginPage />);
    fireEvent.change(screen.getByPlaceholderText("tu@empresa.com"), { target: { value: "ana@example.com" } });
    fireEvent.change(screen.getByPlaceholderText("••••••••"), { target: { value: "una-clave" } });
    fireEvent.click(screen.getByRole("button", { name: t("auth.login.submit") }));

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(t("errors.rate_limited", { seconds: 37 }));
    expect(alerta).not.toHaveTextContent("rate_limited");
  });
});
