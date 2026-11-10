import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createTranslator } from "@/i18n";
import AccesoPage from "./page";

// S6.2 (CA13): la página del enlace de un solo uso.
const canjear = vi.fn();

vi.mock("@/lib/dossier-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dossier-api")>();
  return { ...actual, redeemDossierAccessLink: (token: string) => canjear(token) };
});
vi.mock("@/providers/PreferencesProvider", () => {
  const t = createTranslator("es");
  return { useTranslation: () => ({ t, locale: "es" }) };
});

function conFragmento(hash: string) {
  window.history.replaceState(null, "", `/acceso${hash}`);
}

describe("Página /acceso (S6.2)", () => {
  beforeEach(() => {
    canjear.mockReset();
  });
  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it("no gasta el enlace hasta pulsar «Ver dossier»", async () => {
    conFragmento("#t=TOKEN-1");
    render(<AccesoPage />);

    expect(await screen.findByRole("button", { name: "Ver dossier" })).toBeInTheDocument();
    expect(canjear).not.toHaveBeenCalled();
  });

  it("al pulsar, canjea el token del fragmento y muestra el informe", async () => {
    canjear.mockResolvedValue({
      subject_name: "Ana Prueba",
      body: "## Resumen\n\nAna dirige Empresa de Prueba SA.",
      created_at: "2026-11-10T12:00:00+00:00",
      output_language: "es",
    });
    conFragmento("#t=TOKEN-1");
    render(<AccesoPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Ver dossier" }));

    expect(canjear).toHaveBeenCalledWith("TOKEN-1");
    expect(await screen.findByText("Ana Prueba")).toBeInTheDocument();
    expect(screen.getByText("Ana dirige Empresa de Prueba SA.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Resumen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ver dossier" })).toBeNull();
  });

  it("si el enlace ya no sirve, lo dice y ofrece iniciar sesión", async () => {
    const { DossierApiError } = await import("@/lib/dossier-api");
    canjear.mockRejectedValue(new DossierApiError(410, "El enlace ya no es válido."));
    conFragmento("#t=USADO");
    render(<AccesoPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Ver dossier" }));

    await waitFor(() => expect(screen.getByText(/ya se usó o venció/)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login");
  });

  it("sin token en el enlace no ofrece el botón", async () => {
    conFragmento("");
    render(<AccesoPage />);

    expect(await screen.findByText(/ya se usó o venció/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ver dossier" })).toBeNull();
    expect(canjear).not.toHaveBeenCalled();
  });
});
