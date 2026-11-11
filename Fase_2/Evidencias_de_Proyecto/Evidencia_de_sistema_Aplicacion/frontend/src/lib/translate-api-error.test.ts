import { describe, expect, it } from "vitest";
import { createTranslator } from "@/i18n";
import { SUPPORTED_LOCALES } from "@/i18n/types";
import { DossierApiError } from "@/lib/dossier-api";
import { translateApiErrorMessage } from "@/lib/translate-backend-message";

function passwordError(field = "password") {
  return new DossierApiError(422, `body.${field}: La contraseña supera 72 bytes.`, {
    detail: [{ type: "password_too_long_bytes", loc: ["body", field], ctx: { max_bytes: 72 } }],
  });
}

describe("validación de contraseña de la API", () => {
  it.each(SUPPORTED_LOCALES)("muestra un mensaje comprensible en %s", (locale) => {
    const t = createTranslator(locale);
    const message = translateApiErrorMessage(passwordError(), t);
    expect(message).toContain("72");
    expect(message).not.toBe(t("errors.server_generic"));
    expect(message).not.toContain("body.password");
    expect(message).not.toContain("password_too_long_bytes");
  });
});

describe("validación de la nueva contraseña al cambiarla", () => {
  it.each(SUPPORTED_LOCALES)("muestra el mismo mensaje que el registro en %s", (locale) => {
    const t = createTranslator(locale);
    const message = translateApiErrorMessage(passwordError("new_password"), t);
    expect(message).toBe(t("auth.error.password_max_bytes"));
    expect(message).not.toContain("body.new_password");
  });

  it("no confunde otros campos con el límite de bcrypt", () => {
    const t = createTranslator("es");
    const message = translateApiErrorMessage(passwordError("current_password"), t);
    expect(message).not.toBe(t("auth.error.password_max_bytes"));
  });
});

describe("límite de solicitudes (S5.8)", () => {
  function demasiadas(segundos = 42) {
    return new DossierApiError(429, "rate_limited", {
      detail: { code: "rate_limited", message: "Demasiadas solicitudes.", retry_after: segundos },
    });
  }

  it.each(SUPPORTED_LOCALES)("explica cuánto esperar en %s, sin mostrar el código interno", (locale) => {
    const t = createTranslator(locale);
    const message = translateApiErrorMessage(demasiadas(42), t);
    expect(message).toContain("42");
    expect(message).not.toContain("rate_limited");
    expect(message).not.toBe(t("errors.server_generic"));
  });

  it("sin retry_after usa un minuto", () => {
    const t = createTranslator("es");
    const err = new DossierApiError(429, "rate_limited", { detail: { code: "rate_limited" } });
    expect(translateApiErrorMessage(err, t)).toContain("60");
  });
});

// UX-ADMIN-01: tope de dossiers a la vez según el plan.
describe("tope de dossiers a la vez", () => {
  const limite = (limit: number) =>
    new DossierApiError(409, "CONCURRENT_DOSSIER_LIMIT", {
      detail: { code: "CONCURRENT_DOSSIER_LIMIT", limit, active: limit },
    });

  it.each(SUPPORTED_LOCALES)("explica el tope con su número en %s", (locale) => {
    const t = createTranslator(locale);
    const message = translateApiErrorMessage(limite(3), t);
    expect(message).toBe(t("errors.concurrent_dossier_limit", { limit: 3 }));
    expect(message).toContain("3");
    expect(message).not.toContain("CONCURRENT");
    expect(message).not.toBe("errors.concurrent_dossier_limit");
  });
});
