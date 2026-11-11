/**
 * Retroceso progresivo para reconectar los canales SSE del dashboard (S5.3).
 *
 * Intento n → espera de hasta `min(30 s, 1 s · 2ⁿ)`, con una variación aleatoria entre
 * la mitad y el total. Así un servidor caído no recibe una ráfaga de reconexiones de
 * todas las pestañas a la vez cuando vuelve.
 */
export const RECONNECT_BASE_MS = 1000;
export const RECONNECT_MAX_MS = 30_000;

export function reconnectDelay(attempt: number, random: () => number = Math.random): number {
  const n = Number.isFinite(attempt) ? Math.max(0, Math.floor(attempt)) : 0;
  // 2^15 s ya supera el tope: no hace falta calcular potencias mayores.
  const techo = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * 2 ** Math.min(n, 15));
  return Math.round(techo / 2 + random() * (techo / 2));
}
