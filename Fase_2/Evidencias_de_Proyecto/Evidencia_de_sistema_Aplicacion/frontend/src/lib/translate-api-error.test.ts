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
