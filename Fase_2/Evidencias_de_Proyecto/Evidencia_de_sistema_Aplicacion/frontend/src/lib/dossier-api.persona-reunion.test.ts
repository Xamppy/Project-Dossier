import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchEnqueueGoogleCalendarDossier,
  fetchEnqueueOutlookCalendarDossier,
  persistAuthToken,
} from "@/lib/dossier-api";

describe("UX-CAL-03 · persona elegida al encolar desde el calendario", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    persistAuthToken("jwt-de-prueba", true);
    fetchMock.mockReset();
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ async: true, job_id: "j1" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  const cuerpo = () => JSON.parse(String(fetchMock.mock.calls[0][1].body)) as Record<string, unknown>;

  it.each([
    ["google", fetchEnqueueGoogleCalendarDossier],
    ["outlook", fetchEnqueueOutlookCalendarDossier],
  ] as const)("%s envía persona_id", async (_nombre, encolar) => {
    await encolar({ eventId: "ev1", personaId: "max@acme.test" });
    expect(cuerpo()).toMatchObject({ event_id: "ev1", persona_id: "max@acme.test" });
  });

  it("sin elección envía null, como una reunión de una sola persona", async () => {
    await fetchEnqueueGoogleCalendarDossier({ eventId: "ev1" });
    expect(cuerpo()).toMatchObject({ persona_id: null });
  });
});
