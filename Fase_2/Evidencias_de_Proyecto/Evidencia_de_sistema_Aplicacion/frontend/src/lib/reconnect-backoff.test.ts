import { describe, expect, it } from "vitest";
import { RECONNECT_BASE_MS, RECONNECT_MAX_MS, reconnectDelay } from "./reconnect-backoff";

// S5.3: espera antes de reconectar un canal SSE. Crece 1, 2, 4, 8… s hasta 30 s, con una
// variación entre la mitad y el total para que las pestañas no reconecten todas a la vez.

describe("reconnectDelay", () => {
  it("con la variación al máximo, duplica la espera en cada intento", () => {
    const alMaximo = () => 1;
    expect([0, 1, 2, 3, 4].map((n) => reconnectDelay(n, alMaximo))).toEqual([
      1000, 2000, 4000, 8000, 16000,
    ]);
  });

  it("nunca pasa de 30 s, por muchos intentos que lleve", () => {
    expect(reconnectDelay(5, () => 1)).toBe(RECONNECT_MAX_MS);
    expect(reconnectDelay(50, () => 1)).toBe(RECONNECT_MAX_MS);
    expect(reconnectDelay(5000, () => 1)).toBe(RECONNECT_MAX_MS);
  });

  it("la variación queda entre la mitad y el total de la espera del intento", () => {
    expect(reconnectDelay(0, () => 0)).toBe(RECONNECT_BASE_MS / 2);
    expect(reconnectDelay(3, () => 0)).toBe(4000);
    expect(reconnectDelay(3, () => 0.5)).toBe(6000);
    for (let i = 0; i < 200; i++) {
      const espera = reconnectDelay(2);
      expect(espera).toBeGreaterThanOrEqual(2000);
      expect(espera).toBeLessThanOrEqual(4000);
    }
  });

  it("un intento negativo o no entero se trata como el primero", () => {
    expect(reconnectDelay(-3, () => 1)).toBe(1000);
    expect(reconnectDelay(Number.NaN, () => 1)).toBe(1000);
    expect(reconnectDelay(1.7, () => 1)).toBe(2000);
  });
});
