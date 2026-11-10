import { describe, expect, it } from "vitest";
import { DEFAULT_PREFERENCES } from "@/i18n/types";
import type { AuthUser } from "@/lib/dossier-api";
import { authUserToPreferencesPatch, preferencesToAuthPatch } from "./auth-preferences-sync";

function usuario(extra: Partial<AuthUser> = {}): AuthUser {
  return {
    id: "u-1",
    email: "ana@example.test",
    full_name: "Ana",
    company_name: "Acme",
    organization_id: "o-1",
    role: "user",
    ...extra,
  } as AuthUser;
}

describe("sincronización de preferencias · retención (S6.5, CA12)", () => {
  it("toma el plazo en horas que informa el servidor", () => {
    const patch = authUserToPreferencesPatch(usuario({ dossier_retention_hours: 24 }));
    expect(patch.dossierRetentionHours).toBe(24);
  });

  it("sin dato del servidor no inventa un plazo", () => {
    const patch = authUserToPreferencesPatch(usuario());
    expect(patch).not.toHaveProperty("dossierRetentionHours");
  });

  it("ya no envía dossier_retention_days al servidor", () => {
    const cuerpo = preferencesToAuthPatch({ ...DEFAULT_PREFERENCES, locale: "es" });
    expect(cuerpo).not.toHaveProperty("dossier_retention_days");
    expect(Object.keys(cuerpo).sort()).toEqual(["dossier_output_language", "locale", "timezone"]);
  });

  it("el plazo por omisión es de 24 horas", () => {
    expect(DEFAULT_PREFERENCES.dossierRetentionHours).toBe(24);
  });
});
