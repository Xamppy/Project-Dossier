import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createTranslator } from "@/i18n";
import GeneralPanel from "./GeneralPanel";

// S6.5 (CA12): la retención la fija el servidor; Configuración solo la informa.
const horas = { valor: 24 };

vi.mock("@/providers/PreferencesProvider", () => {
  const t = createTranslator("es");
  return {
    usePreferences: () => ({
      t,
      locale: "es",
      preferences: { theme: "dark", dossierRetentionHours: horas.valor },
      setTheme: () => {},
    }),
  };
});
vi.mock("@/components/settings/ThemePreview", () => ({ default: () => <div /> }));

describe("GeneralPanel · retención de dossiers (S6.5)", () => {
  it("informa el plazo de 24 horas y no ofrece elegirlo", () => {
    horas.valor = 24;
    const { container } = render(<GeneralPanel />);
    expect(screen.getByText(/24 horas después de generarse/)).toBeInTheDocument();
    expect(container.querySelector("select")).toBeNull();
    expect(screen.queryByText("90 días")).toBeNull();
    expect(screen.queryByText("Nunca")).toBeNull();
  });

  it("muestra el plazo que informa el servidor", () => {
    horas.valor = 6;
    render(<GeneralPanel />);
    expect(screen.getByText(/6 horas después de generarse/)).toBeInTheDocument();
  });
});
