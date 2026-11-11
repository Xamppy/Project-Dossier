/**
 * Aviso del sistema operativo cuando llega un dossier nuevo (informe beta del 2026-10-06).
 *
 * La preferencia vive en la cuenta (`users.notify_browser`); aquí se guarda una copia local para
 * no consultar la API en cada aviso. La actualizan el panel de Notificaciones y la barra lateral
 * cada vez que leen la cuenta.
 */
const PREF_KEY = "dossier_notify_browser";

export function setBrowserNotifyPref(on: boolean): void {
  try {
    localStorage.setItem(PREF_KEY, on ? "1" : "0");
  } catch {
    /* sin almacenamiento: no hay avisos */
  }
}

function prefOn(): boolean {
  try {
    return localStorage.getItem(PREF_KEY) !== "0";
  } catch {
    return false;
  }
}

export function browserNotificationsSupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

/** Activado en la cuenta y con permiso del navegador. */
export function browserNotifyEnabled(): boolean {
  return browserNotificationsSupported() && prefOn() && Notification.permission === "granted";
}

/** Pide permiso al navegador; `true` si quedó concedido. */
export async function requestBrowserNotifyPermission(): Promise<boolean> {
  if (!browserNotificationsSupported()) return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  return (await Notification.requestPermission()) === "granted";
}

/** Muestra el aviso; al pulsarlo lleva al dossier. Nunca lanza. */
export function showDossierNotification(title: string, body: string, href: string): void {
  if (!browserNotifyEnabled()) return;
  try {
    const aviso = new Notification(title, { body, tag: href });
    aviso.onclick = () => {
      window.focus();
      window.location.assign(href);
      aviso.close();
    };
  } catch {
    /* algunos navegadores solo permiten avisos desde un service worker */
  }
}
