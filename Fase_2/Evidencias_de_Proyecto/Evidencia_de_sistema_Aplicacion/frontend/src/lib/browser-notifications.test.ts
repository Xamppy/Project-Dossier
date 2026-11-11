import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { browserNotifyEnabled, setBrowserNotifyPref, showDossierNotification } from "./browser-notifications";

// Informe beta: aviso del sistema operativo cuando llega un dossier, si el usuario lo activó.

function navegador(permiso: NotificationPermission) {
  const creados: { title: string; options: NotificationOptions }[] = [];
  const Falso = Object.assign(
    vi.fn(function (this: Record<string, unknown>, title: string, options: NotificationOptions) {
      creados.push({ title, options });
      this.close = vi.fn();
    }),
    { permission: permiso, requestPermission: vi.fn() },
  );
  vi.stubGlobal("Notification", Falso);
  return creados;
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("aviso del navegador", () => {
  it("con la preferencia activada y permiso, avisa con el título del dossier", () => {
    const creados = navegador("granted");
    setBrowserNotifyPref(true);
    showDossierNotification("Acme Corp", "complete", "/dashboard/dossiers/1");
    expect(creados).toEqual([{ title: "Acme Corp", options: { body: "complete", tag: "/dashboard/dossiers/1" } }]);
  });

  it.each([
    ["preferencia apagada", false, "granted"],
    ["sin permiso del navegador", true, "default"],
    ["permiso denegado", true, "denied"],
  ] as const)("%s → no avisa", (_caso, pref, permiso) => {
    const creados = navegador(permiso);
    setBrowserNotifyPref(pref);
    showDossierNotification("Acme", "complete", "/x");
    expect(creados).toEqual([]);
    expect(browserNotifyEnabled()).toBe(false);
  });

  it("sin soporte de notificaciones no falla", () => {
    vi.stubGlobal("Notification", undefined);
    // @ts-expect-error se simula un navegador sin la API
    delete window.Notification;
    expect(browserNotifyEnabled()).toBe(false);
    expect(() => showDossierNotification("Acme", "complete", "/x")).not.toThrow();
  });
});
