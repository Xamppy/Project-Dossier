import { StrictMode, useEffect } from "react";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_ME_CHANGED_EVENT } from "@/hooks/useAuthMe";
import type { DossiersListResponse } from "@/lib/dossier-api";
import {
  DossierNotificationsStreamError,
  type DossierNotificationsStreamErrorKind,
  type DossierNotificationsStreamHandlers,
} from "@/lib/dossier-notifications-stream";
import { NotificationsProvider, useNotifications } from "./NotificationsProvider";

// S5.2 y S5.3. El adaptador SSE se sustituye por un registro de suscripciones que la
// prueba controla; el transporte real se prueba en lib/dossier-notifications-stream.test.ts.

type FakeSub = { handlers: DossierNotificationsStreamHandlers; closed: boolean };

const h = vi.hoisted(() => ({
  subs: [] as FakeSub[],
  fetchDossiersFromApi: vi.fn(),
}));

vi.mock("@/lib/dossier-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dossier-api")>();
  return { ...actual, fetchDossiersFromApi: h.fetchDossiersFromApi };
});
vi.mock("@/lib/dossier-notifications-stream", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dossier-notifications-stream")>();
  return {
    ...actual,
    openDossierNotificationsStream: (handlers: DossierNotificationsStreamHandlers) => {
      const sub: FakeSub = { handlers, closed: false };
      h.subs.push(sub);
      return {
        close: () => {
          sub.closed = true;
        },
      };
    },
  };
});

const BASE = "2026-11-10T10:00:00Z";
const DESPUES = "2026-11-10T11:00:00Z";

function lista(...dossiers: { id: string; name: string; at: string }[]): DossiersListResponse {
  return {
    organization_id: "org",
    items: dossiers.map((d) => ({
      id: d.id,
      subject_name: d.name,
      status: "complete",
      created_at: d.at,
      trigger_source: "manual",
    })),
  } as unknown as DossiersListResponse;
}

function Probe() {
  const { notifications, unreadCount } = useNotifications();
  return (
    <div>
      <span data-testid="unread">{unreadCount}</span>
      <ul>
        {notifications.map((n) => (
          <li key={n.id}>{n.title}</li>
        ))}
      </ul>
    </div>
  );
}

function montar(strict = false) {
  const arbol = (
    <NotificationsProvider>
      <Probe />
    </NotificationsProvider>
  );
  return render(strict ? <StrictMode>{arbol}</StrictMode> : arbol);
}

const abiertas = () => h.subs.filter((s) => !s.closed);

function actual(): FakeSub {
  const subs = abiertas();
  if (subs.length !== 1) throw new Error(`Se esperaba 1 canal abierto y hay ${subs.length}`);
  return subs[0];
}

function recibir(datos: DossiersListResponse) {
  const sub = actual();
  act(() => sub.handlers.onList(datos));
}

function cortar(kind: DossierNotificationsStreamErrorKind, status: number | null = null) {
  const sub = actual();
  act(() => {
    sub.closed = true; // el adaptador real ya cerró cuando avisa el error
    sub.handlers.onError(new DossierNotificationsStreamError(kind, status));
  });
}

function avanzar(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

const sinLeer = () => screen.getByTestId("unread").textContent;

beforeEach(() => {
  vi.useFakeTimers();
  // Variación del retroceso al máximo: esperas exactas de 1, 2, 4… s.
  vi.spyOn(Math, "random").mockReturnValue(1);
  h.subs.length = 0;
  h.fetchDossiersFromApi.mockReset();
  h.fetchDossiersFromApi.mockResolvedValue(lista());
  localStorage.clear();
  localStorage.setItem("dossier_access_token", "tok");
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("NotificationsProvider · canal en vivo (S5.2)", () => {
  it("CA6 · abre un único canal y no sondea: ni setInterval, ni GET /dossiers, ni al recuperar el foco", () => {
    const setIntervalSpy = vi.spyOn(window, "setInterval");
    montar(true);
    expect(abiertas()).toHaveLength(1);

    avanzar(120_000);
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });

    expect(setIntervalSpy).not.toHaveBeenCalled();
    expect(h.fetchDossiersFromApi).not.toHaveBeenCalled();
    expect(abiertas()).toHaveLength(1);
  });

  it("CA6 · la primera lista fija la línea base y un dossier nuevo llega como notificación", () => {
    montar();
    recibir(lista({ id: "d1", name: "Antiguo", at: BASE }));
    expect(sinLeer()).toBe("0");

    recibir(lista({ id: "d2", name: "Acme", at: DESPUES }, { id: "d1", name: "Antiguo", at: BASE }));
    expect(sinLeer()).toBe("1");
    expect(screen.getByText("Acme")).toBeTruthy();
    expect(screen.queryByText("Antiguo")).toBeNull();
  });

  it("la misma lista repetida no duplica notificaciones", () => {
    montar();
    recibir(lista({ id: "d1", name: "Antiguo", at: BASE }));
    const nueva = lista({ id: "d2", name: "Acme", at: DESPUES }, { id: "d1", name: "Antiguo", at: BASE });
    recibir(nueva);
    recibir(nueva);
    expect(sinLeer()).toBe("1");
    expect(screen.getAllByText("Acme")).toHaveLength(1);
  });
});

describe("NotificationsProvider · reconexión con retroceso (S5.3)", () => {
  it("CA7 · tras un corte reconecta solo con esperas de 1, 2 y 4 s", () => {
    montar();
    cortar("network");
    expect(abiertas()).toHaveLength(0);
    avanzar(999);
    expect(abiertas()).toHaveLength(0);
    avanzar(1);
    expect(abiertas()).toHaveLength(1);

    cortar("http", 502);
    avanzar(1999);
    expect(abiertas()).toHaveLength(0);
    avanzar(1);
    expect(abiertas()).toHaveLength(1);

    cortar("closed");
    avanzar(3999);
    expect(abiertas()).toHaveLength(0);
    avanzar(1);
    expect(abiertas()).toHaveLength(1);
  });

  it("CA7 · al recibir datos el retroceso vuelve a empezar", () => {
    montar();
    cortar("network");
    avanzar(1000);
    cortar("network");
    avanzar(2000);
    recibir(lista({ id: "d1", name: "Antiguo", at: BASE }));

    cortar("network");
    avanzar(1000);
    expect(abiertas()).toHaveLength(1);
  });

  it("CA7 · la espera no pasa de 30 s aunque el servidor siga caído", () => {
    montar();
    for (let i = 0; i < 8; i++) {
      cortar("network");
      avanzar(30_000);
      expect(abiertas()).toHaveLength(1);
    }
    expect(h.subs).toHaveLength(9);
  });

  it("CA7 · tras el corte programado del servidor vuelven a llegar notificaciones sin recargar", () => {
    montar();
    recibir(lista({ id: "d1", name: "Antiguo", at: BASE }));
    cortar("closed");
    avanzar(1000);
    recibir(lista({ id: "d2", name: "Tras reconectar", at: DESPUES }, { id: "d1", name: "Antiguo", at: BASE }));
    expect(screen.getByText("Tras reconectar")).toBeTruthy();
    expect(sinLeer()).toBe("1");
  });

  it.each(["unauthorized", "forbidden"] as const)(
    "CA8 · con %s no se reintenta",
    (kind) => {
      montar();
      cortar(kind, kind === "unauthorized" ? 401 : 403);
      avanzar(10 * 60_000);
      expect(h.subs).toHaveLength(1);
    },
  );

  it("CA8 · un cambio de sesión cierra el canal y abre otro (también tras un 401)", () => {
    montar();
    const primero = actual();
    act(() => {
      window.dispatchEvent(new Event(AUTH_ME_CHANGED_EVENT));
    });
    expect(primero.closed).toBe(true);
    expect(abiertas()).toHaveLength(1);

    cortar("unauthorized", 401);
    act(() => {
      window.dispatchEvent(new Event(AUTH_ME_CHANGED_EVENT));
    });
    expect(abiertas()).toHaveLength(1);
  });

  it("CA8 · sin sesión no abre el canal; lo abre cuando la sesión aparece", () => {
    localStorage.removeItem("dossier_access_token");
    montar();
    avanzar(60_000);
    expect(h.subs).toHaveLength(0);

    localStorage.setItem("dossier_access_token", "tok");
    act(() => {
      window.dispatchEvent(new Event(AUTH_ME_CHANGED_EVENT));
    });
    expect(abiertas()).toHaveLength(1);
  });

  it("CA9 · al volver la red reconecta enseguida, sin esperar el retroceso", () => {
    montar();
    cortar("network");
    avanzar(1000);
    cortar("network");
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(abiertas()).toHaveLength(1);
    // La espera pendiente quedó cancelada: no abre un segundo canal.
    avanzar(5000);
    expect(abiertas()).toHaveLength(1);
    expect(h.subs).toHaveLength(3);
  });

  it("CA9 · el evento online con el canal abierto no abre otro", () => {
    montar();
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(h.subs).toHaveLength(1);
  });

  it("desmontar cierra el canal y cancela la reconexión pendiente", () => {
    const vista = montar();
    cortar("network");
    vista.unmount();
    avanzar(60_000);
    expect(h.subs).toHaveLength(1);

    const otra = montar();
    const sub = actual();
    otra.unmount();
    expect(sub.closed).toBe(true);
  });

  it("refresh() pide la lista una vez, a demanda (no es un sondeo)", async () => {
    const captura: { refresh: (() => void) | null } = { refresh: null };
    function ConRefresh() {
      const { refresh } = useNotifications();
      useEffect(() => {
        captura.refresh = refresh;
      });
      return null;
    }
    render(
      <NotificationsProvider>
        <ConRefresh />
      </NotificationsProvider>,
    );
    await act(async () => {
      captura.refresh?.();
    });
    expect(h.fetchDossiersFromApi).toHaveBeenCalledTimes(1);
    expect(h.fetchDossiersFromApi).toHaveBeenCalledWith(25);
  });
});

describe("NotificationsProvider · aviso del navegador (informe beta)", () => {
  function navegador() {
    const creados: string[] = [];
    vi.stubGlobal(
      "Notification",
      Object.assign(
        vi.fn(function (this: Record<string, unknown>, title: string) {
          creados.push(title);
        }),
        { permission: "granted", requestPermission: vi.fn() },
      ),
    );
    return creados;
  }

  it("avisa una sola vez por cada dossier nuevo, solo si está activado", () => {
    const creados = navegador();
    localStorage.setItem("dossier_notify_browser", "1");
    montar();
    recibir(lista({ id: "d1", name: "Antiguo", at: BASE }));
    const nueva = lista({ id: "d2", name: "Acme", at: DESPUES }, { id: "d1", name: "Antiguo", at: BASE });
    recibir(nueva);
    recibir(nueva);
    expect(creados).toEqual(["Acme"]);
    vi.unstubAllGlobals();
  });

  it("con la preferencia apagada no avisa", () => {
    const creados = navegador();
    localStorage.setItem("dossier_notify_browser", "0");
    montar();
    recibir(lista({ id: "d1", name: "Antiguo", at: BASE }));
    recibir(lista({ id: "d2", name: "Acme", at: DESPUES }, { id: "d1", name: "Antiguo", at: BASE }));
    expect(creados).toEqual([]);
    vi.unstubAllGlobals();
  });
});
