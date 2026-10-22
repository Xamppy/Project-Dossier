import { describe, expect, it } from "vitest";

import nextConfig from "../../next.config";

// Next 16.3 escribe frontend/AGENTS.md y frontend/CLAUDE.md al arrancar
// `next dev` si detecta un agente de código. El repositorio ya tiene su
// AGENTS.md y CLAUDE.md raíz como fuente única de instrucciones; dos archivos
// generados que dicen otra cosa confunden a los agentes. Ver CHORE-2026-10-19-01.
describe("next.config", () => {
  it("desactiva la generación de instrucciones de agente en next dev", () => {
    expect(nextConfig.agentRules).toBe(false);
  });
});
