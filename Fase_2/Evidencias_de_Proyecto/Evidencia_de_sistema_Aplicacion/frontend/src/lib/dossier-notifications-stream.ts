/**
 * Canal SSE de notificaciones del dashboard (S5.2).
 *
 * Consume `GET /dossier-notifications/stream`: un evento `dossiers` al conectar y otro
 * cada vez que cambia la lista, con el mismo cuerpo que `GET /dossiers?limit=25`.
 * Usa `@microsoft/fetch-event-source` como el canal de jobs (S5.1, ADR 0006): el JWT
 * va en `Authorization`, nunca en la URL.
 *
 * Una conexión por suscripción y ningún reintento propio: cualquier corte termina la
 * suscripción con un `DossierNotificationsStreamError` y quien la abrió decide cuándo
 * reconectar (S5.3, `NotificationsProvider` con `reconnectDelay`).
 */
import { fetchEventSource, type EventSourceMessage } from "@microsoft/fetch-event-source";
import {
  authFetch,
  getApiBaseUrl,
  getStoredAccessToken,
  type DossiersListResponse,
} from "@/lib/dossier-api";

export type DossierNotificationsStreamErrorKind =
  /** 401 o sin token guardado. No conviene reintentar hasta que cambie la sesión. */
  | "unauthorized"
  /** 403: sin acceso a la organización. Tampoco se reintenta. */
  | "forbidden"
  /** Cualquier otro estado HTTP (5xx, 429…). */
  | "http"
  /** `fetch` falló o la lectura se cortó. */
  | "network"
  /** El servidor cerró el canal (su corte de seguridad a los 600 s, un reinicio…). */
  | "closed"
  /** Content-Type ajeno a SSE o un evento `dossiers` con payload inválido. */
  | "protocol";

export class DossierNotificationsStreamError extends Error {
  readonly kind: DossierNotificationsStreamErrorKind;
  readonly status: number | null;

  constructor(kind: DossierNotificationsStreamErrorKind, status: number | null = null) {
    super(kind);
    this.name = "DossierNotificationsStreamError";
    this.kind = kind;
    this.status = status;
  }
}

export type DossierNotificationsStreamHandlers = {
  /** Lista de dossiers ya validada. */
  onList: (list: DossiersListResponse) => void;
  /** Se llama como mucho una vez; después la suscripción ya está cerrada. */
  onError: (error: DossierNotificationsStreamError) => void;
};

export type DossierNotificationsStreamSubscription = {
  /** Cierra la lectura sin avisar error. */
  close: () => void;
};

const EVENTO = "dossiers";

/** Valida en ejecución el cuerpo de un evento `dossiers`; `null` si no sirve. */
export function parseDossiersList(data: unknown): DossiersListResponse | null {
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  const o = data as Record<string, unknown>;
  if (!Array.isArray(o.items)) return null;
  return o as unknown as DossiersListResponse;
}

function errorForStatus(status: number): DossierNotificationsStreamError {
  if (status === 401) return new DossierNotificationsStreamError("unauthorized", status);
  if (status === 403) return new DossierNotificationsStreamError("forbidden", status);
  return new DossierNotificationsStreamError("http", status);
}

export function openDossierNotificationsStream(
  handlers: DossierNotificationsStreamHandlers,
): DossierNotificationsStreamSubscription {
  const controller = new AbortController();
  let finished = false;

  function finish() {
    finished = true;
    controller.abort();
  }

  function fail(error: DossierNotificationsStreamError) {
    if (finished) return;
    finish();
    handlers.onError(error);
  }

  const subscription: DossierNotificationsStreamSubscription = { close: finish };

  const token = getStoredAccessToken();
  if (!token) {
    // Asíncrono, como cualquier otro error: quien abre no recibe callbacks durante la llamada.
    queueMicrotask(() => fail(new DossierNotificationsStreamError("unauthorized")));
    return subscription;
  }

  fetchEventSource(`${getApiBaseUrl()}/dossier-notifications/stream`, {
    method: "GET",
    // En minúsculas: la librería añade `accept` si no lo encuentra con ese nombre.
    headers: { accept: "text/event-stream", authorization: `Bearer ${token}` },
    signal: controller.signal,
    // Sin esto la librería corta y reabre la conexión cada vez que cambia la visibilidad.
    openWhenHidden: true,
    // S3.9: si el token de acceso venció, `authFetch` lo renueva y reabre una vez.
    fetch: (input, init) => {
      const respuesta = authFetch(input, init);
      // Al cerrar el canal se cancela la petición: esa cancelación es esperada, no un error.
      respuesta.catch(() => undefined);
      return respuesta;
    },
    async onopen(response) {
      if (!response.ok) throw errorForStatus(response.status);
      const contentType = response.headers.get("content-type") ?? "";
      if (!contentType.startsWith("text/event-stream")) {
        throw new DossierNotificationsStreamError("protocol", response.status);
      }
    },
    onmessage(message: EventSourceMessage) {
      if (finished) return;
      // Latido (`: ping`) y eventos ajenos no traen la lista.
      if (!message.data || message.event !== EVENTO) return;
      let parsed: unknown;
      try {
        parsed = JSON.parse(message.data);
      } catch {
        throw new DossierNotificationsStreamError("protocol");
      }
      const list = parseDossiersList(parsed);
      if (!list) throw new DossierNotificationsStreamError("protocol");
      handlers.onList(list);
    },
    onclose() {
      if (!finished) throw new DossierNotificationsStreamError("closed");
    },
    onerror(err: unknown) {
      // Lanzar detiene la librería: sin esto reintenta cada segundo para siempre.
      throw err instanceof DossierNotificationsStreamError
        ? err
        : new DossierNotificationsStreamError("network");
    },
  }).catch((err: unknown) => {
    fail(
      err instanceof DossierNotificationsStreamError
        ? err
        : new DossierNotificationsStreamError("network"),
    );
  });

  return subscription;
}
