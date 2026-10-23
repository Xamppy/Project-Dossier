"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import {
  clearAuthSession,
  DossierApiError,
  fetchAuthMe,
  getStoredAccessToken,
} from "@/lib/dossier-api";
import { useTranslation, usePreferences } from "@/providers/PreferencesProvider";

function redirectToLogin(pathname: string, reason?: "session_expired") {
  const next = pathname.startsWith("/dashboard") ? pathname : "/dashboard";
  const params = new URLSearchParams({ next });
  if (reason) params.set("reason", reason);
  window.location.replace(`/login?${params.toString()}`);
}

/**
 * Exige sesión (JWT en localStorage o sessionStorage) para ver el dashboard.
 * Valida el token contra la API; si está expirado o es inválido, fuerza nuevo login.
 */
export default function DashboardAuthGate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { t } = useTranslation();
  const { hydrateFromAuthUser } = usePreferences();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      const token = getStoredAccessToken();
      const path = pathname || "/dashboard";
      if (!token) {
        redirectToLogin(path);
        return;
      }
      try {
        const me = await fetchAuthMe();
        hydrateFromAuthUser(me);
        if (!cancelled) setAllowed(true);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof DossierApiError && e.status === 401) {
          clearAuthSession();
          redirectToLogin(path, "session_expired");
          return;
        }
        // Red u otro error: dejar entrar; las vistas mostrarán su propio aviso.
        setAllowed(true);
      }
    }

    void check();
    return () => {
      cancelled = true;
    };
  }, [pathname, hydrateFromAuthUser]);

  if (!allowed) {
    return (
      <div
        className="flex min-h-screen items-center justify-center px-4"
        style={{ backgroundColor: "var(--bg-page)" }}
      >
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {t("auth.gate_checking")}
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
