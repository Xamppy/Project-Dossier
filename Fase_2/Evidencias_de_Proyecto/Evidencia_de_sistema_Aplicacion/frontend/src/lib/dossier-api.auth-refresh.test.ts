/**
 * S3.9 · Renovación del token de acceso (15 min) con la cookie HttpOnly de renovación.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AUTH_TOKEN_STORAGE_KEY,
  authFetch,
  authLogin,
  clearAuthSession,
  fetchDashboardSummary,
  getStoredAccessToken,
  persistAuthToken,
  refreshAccessToken,
} from "./dossier-api";

function json(cuerpo: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json" } })
  );
}

function ruta(url: unknown): string {
  return new URL(String(url)).pathname;
}

function bearer(init: unknown): string | null {
  return new Headers((init as RequestInit | undefined)?.headers).get("authorization");
}

const RESUMEN_MINIMO = {
  as_of: "x",
  timezone: "UTC",
  upcoming: { state: "ok" },
  preparation_cost: { state: "ok" },
  credits: { state: "ok" },
};

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

describe("authFetch", () => {
  it("ante un 401 renueva el token y reintenta una vez con el nuevo", async () => {
    persistAuthToken("viejo", true);
    const fetchMock = vi.fn((url: unknown, init?: RequestInit) => {
      if (ruta(url) === "/auth/refresh") return json({ access_token: "nuevo" });
      return bearer(init) === "Bearer nuevo" ? json({ ok: true }) : json({ detail: "vencido" }, 401);
    });
    vi.stubGlobal("fetch", fetchMock);

    const r = await authFetch("http://api.test/dossiers", { headers: { Authorization: "Bearer viejo" } });

    expect(r.status).toBe(200);
    expect(getStoredAccessToken()).toBe("nuevo");
    const rutas = fetchMock.mock.calls.map(([u]) => ruta(u));
    expect(rutas).toEqual(["/dossiers", "/auth/refresh", "/dossiers"]);
    const [, initRefresh] = fetchMock.mock.calls[1];
    expect((initRefresh as RequestInit).credentials).toBe("include");
    expect(bearer(initRefresh)).toBeNull(); // la renovación usa la cookie, nunca el Bearer
  });

  it("si la renovación falla devuelve el 401 original sin reintentar", async () => {
    persistAuthToken("viejo", true);
    const fetchMock = vi.fn((url: unknown) =>
      ruta(url) === "/auth/refresh"
        ? json({ detail: { code: "refresh_expired" } }, 401)
        : json({ detail: "vencido" }, 401)
    );
    vi.stubGlobal("fetch", fetchMock);

    const r = await authFetch("http://api.test/dossiers", { headers: { Authorization: "Bearer viejo" } });

    expect(r.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(getStoredAccessToken()).toBe("viejo");
  });

  it("sin Authorization no intenta renovar", async () => {
    const fetchMock = vi.fn(() => json({ detail: "no" }, 401));
    vi.stubGlobal("fetch", fetchMock);

    const r = await authFetch("http://api.test/organization/invites/preview");

    expect(r.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("un error distinto de 401 no dispara la renovación", async () => {
    persistAuthToken("vigente", true);
    const fetchMock = vi.fn(() => json({ detail: "prohibido" }, 403));
    vi.stubGlobal("fetch", fetchMock);

    const r = await authFetch("http://api.test/x", { headers: { Authorization: "Bearer vigente" } });

    expect(r.status).toBe(403);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("si otra llamada ya renovó, reintenta con el token vigente sin pedir otra renovación", async () => {
    persistAuthToken("ya-renovado", true);
    const fetchMock = vi.fn((_url: unknown, init?: RequestInit) =>
      bearer(init) === "Bearer ya-renovado" ? json({ ok: true }) : json({ detail: "vencido" }, 401)
    );
    vi.stubGlobal("fetch", fetchMock);

    const r = await authFetch("http://api.test/x", { headers: { Authorization: "Bearer viejo" } });

    expect(r.status).toBe(200);
    expect(fetchMock.mock.calls.map(([u]) => ruta(u))).toEqual(["/x", "/x"]);
  });
});

describe("refreshAccessToken", () => {
  it("varias llamadas simultáneas comparten una sola petición", async () => {
    persistAuthToken("viejo", true);
    const fetchMock = vi.fn(() => json({ access_token: "nuevo" }));
    vi.stubGlobal("fetch", fetchMock);

    const tokens = await Promise.all([refreshAccessToken(), refreshAccessToken(), refreshAccessToken()]);

    expect(tokens).toEqual(["nuevo", "nuevo", "nuevo"]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reintenta una vez si otra pestaña acababa de rotar la cookie", async () => {
    persistAuthToken("viejo", true);
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => json({ detail: { code: "refresh_rotated" } }, 401))
      .mockImplementationOnce(() => json({ access_token: "nuevo" }));
    vi.stubGlobal("fetch", fetchMock);

    expect(await refreshAccessToken()).toBe("nuevo");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("una sesión sin recordar sigue guardándose en sessionStorage", async () => {
    persistAuthToken("viejo", false);
    vi.stubGlobal("fetch", vi.fn(() => json({ access_token: "nuevo" })));

    await refreshAccessToken();

    expect(sessionStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("nuevo");
    expect(localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBeNull();
  });

  it("sin red devuelve null", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    expect(await refreshAccessToken()).toBeNull();
  });
});

describe("integración con el resto de la API", () => {
  it("una llamada real del dashboard se recupera de un token vencido", async () => {
    persistAuthToken("viejo", true);
    vi.stubGlobal(
      "fetch",
      vi.fn((url: unknown, init?: RequestInit) => {
        if (ruta(url) === "/auth/refresh") return json({ access_token: "nuevo" });
        return bearer(init) === "Bearer nuevo" ? json(RESUMEN_MINIMO) : json({ detail: "vencido" }, 401);
      })
    );

    await expect(fetchDashboardSummary()).resolves.toMatchObject({ timezone: "UTC" });
  });

  it("el login envía «recuérdame» y acepta la cookie de la API", async () => {
    const fetchMock = vi.fn(() =>
      json({ access_token: "t", token_type: "bearer", user: { id: "u", email: "a@b.cl" } })
    );
    vi.stubGlobal("fetch", fetchMock);

    await authLogin({ email: "a@b.cl", password: "x", remember: false });

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.credentials).toBe("include");
    expect(JSON.parse(String(init.body))).toMatchObject({ remember: false });
  });

  it("cerrar sesión pide revocar la cookie de renovación", async () => {
    persistAuthToken("t", true);
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })));
    vi.stubGlobal("fetch", fetchMock);

    clearAuthSession();

    expect(getStoredAccessToken()).toBeNull();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(ruta(url)).toBe("/auth/logout");
    expect(init).toMatchObject({ method: "POST", credentials: "include" });
  });
});
