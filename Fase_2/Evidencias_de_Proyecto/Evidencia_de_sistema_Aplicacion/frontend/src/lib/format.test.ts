import { afterEach, describe, expect, it, vi } from "vitest";
import { formatCalendarMeetingInstant } from "./format";

// BUG-2026-10-19-09: el aviso de generación mostraba una reunión de las 17:00 (Santiago) como
// 20:00. Las preferencias por omisión traen `timezone: "UTC"` con «seguir al sistema» activo, y
// el formateador usaba ese "UTC" en vez de la zona efectiva del dispositivo.
const REUNION = "2026-10-19T20:00:00Z"; // 17:00 en America/Santiago (UTC−3)

function navegadorEn(zona: string) {
  const real = Intl.DateTimeFormat.prototype.resolvedOptions;
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockImplementation(function (
    this: Intl.DateTimeFormat,
  ) {
    return { ...real.call(this), timeZone: zona };
  });
}

describe("formatCalendarMeetingInstant · zona horaria", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("con «seguir al sistema» usa la zona del dispositivo, no el UTC guardado", () => {
    navegadorEn("America/Santiago");
    const texto = formatCalendarMeetingInstant(REUNION, {
      locale: "es",
      timezone: "UTC",
      timezoneFollowSystem: true,
    });
    expect(texto).toContain("17:00");
    expect(texto).toContain("19/10/2026");
  });

  it("con una zona elegida a mano, usa esa zona", () => {
    navegadorEn("America/Santiago");
    const texto = formatCalendarMeetingInstant(REUNION, {
      locale: "es",
      timezone: "Europe/Madrid",
      timezoneFollowSystem: false,
    });
    expect(texto).toContain("22:00");
  });

  it("sin el dato de «seguir al sistema», respeta la zona guardada", () => {
    const texto = formatCalendarMeetingInstant(REUNION, { locale: "es", timezone: "America/Santiago" });
    expect(texto).toContain("17:00");
  });

  it("una fecha inválida no rompe: devuelve el texto recortado", () => {
    expect(formatCalendarMeetingInstant("no-es-fecha", { locale: "es", timezone: "UTC" })).toBe("no-es-fecha");
  });
});
