import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createTranslator } from "@/i18n";
import { DossierApiError } from "@/lib/dossier-api";
import NotificationsPanel from "./NotificationsPanel";

// Informe beta (2026-10-06): «el estado de cada tipo de notificación no se guarda de forma persistente».

const api = vi.hoisted(() => ({
  fetchAuthMe: vi.fn(),
  patchAuthUserPreferences: vi.fn(),
}));

vi.mock("@/lib/dossier-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dossier-api")>();
  return { ...actual, ...api, getStoredAccessToken: () => "tok" };
});
vi.mock("@/providers/PreferencesProvider", () => {
  const t = createTranslator("es");
  return { useTranslation: () => ({ t, locale: "es" }) };
});

const t = createTranslator("es");
const fila = (key: Parameters<typeof t>[0]) => screen.getByText(t(key)).closest("li") as HTMLElement;
const interruptor = (key: Parameters<typeof t>[0]) => within(fila(key)).getByRole("switch");

function navegadorConPermiso(permiso: NotificationPermission, alPedir: NotificationPermission = permiso) {
  const Falso = Object.assign(vi.fn(), {
    permission: permiso,
    requestPermission: vi.fn(async () => alPedir),
  });
  vi.stubGlobal("Notification", Falso);
  return Falso;
}

beforeEach(() => {
  localStorage.clear();
  api.fetchAuthMe.mockReset().mockResolvedValue({ notify_email: true, notify_browser: false });
  api.patchAuthUserPreferences.mockReset().mockImplementation(async (patch: Record<string, boolean>) => ({
    notify_email: patch.notify_email ?? true,
    notify_browser: patch.notify_browser ?? false,
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Preferencias de notificación", () => {
  it("muestra lo guardado en la cuenta", async () => {
    render(<NotificationsPanel />);
    expect(await screen.findByText(t("notif.email_label"))).toBeTruthy();
    await vi.waitFor(() => expect(interruptor("notif.email_label").getAttribute("aria-checked")).toBe("true"));
    expect(interruptor("notif.browser_label").getAttribute("aria-checked")).toBe("false");
  });

  it("apagar el correo se guarda en la cuenta", async () => {
    const user = userEvent.setup();
    render(<NotificationsPanel />);
    await vi.waitFor(() => expect(interruptor("notif.email_label").getAttribute("aria-checked")).toBe("true"));
    await user.click(interruptor("notif.email_label"));
    expect(api.patchAuthUserPreferences).toHaveBeenCalledWith({ notify_email: false });
    await vi.waitFor(() => expect(interruptor("notif.email_label").getAttribute("aria-checked")).toBe("false"));
  });

  it("activar el navegador pide permiso y, si lo dan, lo guarda", async () => {
    const user = userEvent.setup();
    const Notif = navegadorConPermiso("default", "granted");
    render(<NotificationsPanel />);
    await vi.waitFor(() => expect(interruptor("notif.browser_label").hasAttribute("disabled")).toBe(false));
    await user.click(interruptor("notif.browser_label"));
    expect(Notif.requestPermission).toHaveBeenCalled();
    expect(api.patchAuthUserPreferences).toHaveBeenCalledWith({ notify_browser: true });
    expect(localStorage.getItem("dossier_notify_browser")).toBe("1");
  });

  it("si el navegador bloquea el permiso, no se activa y lo explica", async () => {
    const user = userEvent.setup();
    navegadorConPermiso("default", "denied");
    render(<NotificationsPanel />);
    await vi.waitFor(() => expect(interruptor("notif.browser_label").hasAttribute("disabled")).toBe(false));
    await user.click(interruptor("notif.browser_label"));
    expect(await screen.findByRole("alert")).toHaveTextContent(t("notif.browser_blocked"));
    expect(api.patchAuthUserPreferences).not.toHaveBeenCalled();
    expect(interruptor("notif.browser_label").getAttribute("aria-checked")).toBe("false");
  });

  it("si guardar falla, vuelve al estado anterior y avisa", async () => {
    const user = userEvent.setup();
    api.patchAuthUserPreferences.mockRejectedValue(new DossierApiError(500, "boom"));
    render(<NotificationsPanel />);
    await vi.waitFor(() => expect(interruptor("notif.email_label").getAttribute("aria-checked")).toBe("true"));
    await user.click(interruptor("notif.email_label"));
    expect(await screen.findByRole("alert")).toHaveTextContent(t("notif.save_error"));
    expect(interruptor("notif.email_label").getAttribute("aria-checked")).toBe("true");
  });

  it("alertas de riesgo y resumen semanal están marcadas «Próximamente» y no se pueden activar", async () => {
    render(<NotificationsPanel />);
    for (const key of ["notif.risk_label", "notif.weekly_label"] as const) {
      expect(within(fila(key)).getByText(t("notif.coming_soon"))).toBeTruthy();
      expect(interruptor(key).hasAttribute("disabled")).toBe(true);
    }
  });
});
