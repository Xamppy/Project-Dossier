import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DossierNotificationsStreamError,
  openDossierNotificationsStream,
  type DossierNotificationsStreamHandlers,
} from "@/lib/dossier-notifications-stream";

// Transporte real (S5.2): la librería @microsoft/fetch-event-source corre de verdad y
// solo `fetch` está simulado, como en dossier-job-stream.test.ts.

const LISTA = {
  organization_id: "org-1",
  items: [{ id: "d1", subject_name: "Acme", status: "complete", created_at: "2026-11-10T10:00:00Z" }],
};

function frame(data: unknown, id: number, event = "dossiers"): string {
  return `id: ${id}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function sseBody(contentType = "text/event-stream; charset=utf-8", status = 200) {
  let ctrl!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      ctrl = c;
    },
  });
  const enc = new TextEncoder();
  return {
    response: new Response(body, { status, headers: { "Content-Type": contentType } }),
    push: (text: string) => ctrl.enqueue(enc.encode(text)),
    end: () => ctrl.close(),
  };
}

function handlers() {
  return {
    onList: vi.fn<DossierNotificationsStreamHandlers["onList"]>(),
    onError: vi.fn<DossierNotificationsStreamHandlers["onError"]>(),
  };
}

const tick = () => new Promise((r) => setTimeout(r, 0));
async function until(cond: () => boolean) {
  for (let i = 0; i < 50 && !cond(); i++) await tick();
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  localStorage.setItem("dossier_access_token", "tok-123");
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("openDossierNotificationsStream", () => {
  it("abre el canal con prefijo de API, Bearer y Accept SSE, sin token en la URL", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.dossier.test/api/");
    const sse = sseBody();
    fetchMock.mockResolvedValue(sse.response);
    const h = handlers();
    const sub = openDossierNotificationsStream(h);
    await until(() => fetchMock.mock.calls.length > 0);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.dossier.test/api/dossier-notifications/stream");
    expect(url).not.toContain("tok-123");
    const headers = new Headers(init.headers);
    expect(headers.get("authorization")).toBe("Bearer tok-123");
    expect(headers.get("accept")).toBe("text/event-stream");
    sub.close();
  });

  it("entrega cada lista recibida, también si llega en trozos, e ignora el latido", async () => {
    const sse = sseBody();
    fetchMock.mockResolvedValue(sse.response);
    const h = handlers();
    const sub = openDossierNotificationsStream(h);
    await until(() => fetchMock.mock.calls.length > 0);

    const texto = frame(LISTA, 1);
    sse.push(texto.slice(0, 20));
    sse.push(texto.slice(20));
    sse.push(": ping\n\n");
    sse.push(frame({ ...LISTA, items: [] }, 2));
    await until(() => h.onList.mock.calls.length === 2);

    expect(h.onList.mock.calls.map((c) => c[0])).toEqual([LISTA, { ...LISTA, items: [] }]);
    expect(h.onError).not.toHaveBeenCalled();
    sub.close();
  });

  it("ignora eventos desconocidos", async () => {
    const sse = sseBody();
    fetchMock.mockResolvedValue(sse.response);
    const h = handlers();
    const sub = openDossierNotificationsStream(h);
    await until(() => fetchMock.mock.calls.length > 0);
    sse.push(frame({ x: 1 }, 1, "otra_cosa"));
    sse.push(frame(LISTA, 2));
    await until(() => h.onList.mock.calls.length === 1);
    expect(h.onList).toHaveBeenCalledTimes(1);
    sub.close();
  });

  it.each([
    [401, "unauthorized"],
    [403, "forbidden"],
    [500, "http"],
    [429, "http"],
  ] as const)("HTTP %i → error %s, una sola vez y sin reintento propio de la librería", async (status, kind) => {
    fetchMock.mockResolvedValue(new Response("x", { status }));
    const h = handlers();
    openDossierNotificationsStream(h);
    await until(() => h.onError.mock.calls.length > 0);
    await new Promise((r) => setTimeout(r, 30));

    expect(h.onError).toHaveBeenCalledTimes(1);
    const err = h.onError.mock.calls[0][0];
    expect(err).toBeInstanceOf(DossierNotificationsStreamError);
    expect(err.kind).toBe(kind);
    // Con 401, `authFetch` intenta una vez renovar el token (S3.9); el canal se pide una sola vez.
    const aperturas = fetchMock.mock.calls.filter(([url]) =>
      String(url).includes("/dossier-notifications/stream"),
    );
    expect(aperturas).toHaveLength(1);
  });

  it("sin token no abre la conexión: error unauthorized asíncrono", async () => {
    localStorage.removeItem("dossier_access_token");
    const h = handlers();
    openDossierNotificationsStream(h);
    expect(h.onError).not.toHaveBeenCalled();
    await tick();
    expect(h.onError.mock.calls[0][0].kind).toBe("unauthorized");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("si el servidor cierra el canal (corte de 600 s) avisa como closed", async () => {
    const sse = sseBody();
    fetchMock.mockResolvedValue(sse.response);
    const h = handlers();
    openDossierNotificationsStream(h);
    await until(() => fetchMock.mock.calls.length > 0);
    sse.push(frame(LISTA, 1));
    sse.end();
    await until(() => h.onError.mock.calls.length > 0);
    expect(h.onList).toHaveBeenCalledTimes(1);
    expect(h.onError.mock.calls[0][0].kind).toBe("closed");
  });

  it("un fallo de red da network", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const h = handlers();
    openDossierNotificationsStream(h);
    await until(() => h.onError.mock.calls.length > 0);
    expect(h.onError.mock.calls[0][0].kind).toBe("network");
  });

  it.each([
    ["Content-Type ajeno", () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } })],
  ])("%s → protocol", async (_n, respuesta) => {
    fetchMock.mockResolvedValue(respuesta());
    const h = handlers();
    openDossierNotificationsStream(h);
    await until(() => h.onError.mock.calls.length > 0);
    expect(h.onError.mock.calls[0][0].kind).toBe("protocol");
  });

  it.each([
    ["JSON roto", "id: 1\nevent: dossiers\ndata: {no-json\n\n"],
    ["sin items", frame({ organization_id: "o" }, 1)],
    ["items no es lista", frame({ organization_id: "o", items: "x" }, 1)],
  ])("payload inválido (%s) → protocol y no entrega nada", async (_n, texto) => {
    const sse = sseBody();
    fetchMock.mockResolvedValue(sse.response);
    const h = handlers();
    openDossierNotificationsStream(h);
    await until(() => fetchMock.mock.calls.length > 0);
    sse.push(texto);
    await until(() => h.onError.mock.calls.length > 0);
    expect(h.onList).not.toHaveBeenCalled();
    expect(h.onError.mock.calls[0][0].kind).toBe("protocol");
  });

  it("close() corta la lectura y no avisa error", async () => {
    const sse = sseBody();
    fetchMock.mockResolvedValue(sse.response);
    const h = handlers();
    const sub = openDossierNotificationsStream(h);
    await until(() => fetchMock.mock.calls.length > 0);
    sub.close();
    await new Promise((r) => setTimeout(r, 20));
    expect(h.onError).not.toHaveBeenCalled();
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.signal?.aborted).toBe(true);
  });
});
