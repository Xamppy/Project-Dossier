"use client";

/**
 * S6.2 · Página pública del enlace de un solo uso que llega en el correo.
 *
 * El token viene en el fragmento (`/acceso#t=…`), que nunca llega a un servidor. La página no lo
 * gasta al abrirse (los filtros de correo abren los enlaces para revisarlos): se gasta al pulsar
 * «Ver dossier». Después se borra de la barra de direcciones.
 */
import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import AuthShell from "@/components/AuthShell";
import PrimaryButton from "@/components/PrimaryButton";
import { DossierApiError, redeemDossierAccessLink, type DossierAccessResult } from "@/lib/dossier-api";
import { useTranslation } from "@/providers/PreferencesProvider";

type Accion =
  | { tipo: "inicial" }
  | { tipo: "abriendo" }
  | { tipo: "error" }
  | { tipo: "invalido" }
  | { tipo: "visto"; dossier: DossierAccessResult };

function tokenDelFragmento(): string {
  const fragmento = window.location.hash.replace(/^#/, "");
  return new URLSearchParams(fragmento).get("t")?.trim() ?? "";
}

function alCambiarElFragmento(avisar: () => void): () => void {
  window.addEventListener("hashchange", avisar);
  return () => window.removeEventListener("hashchange", avisar);
}

export default function AccesoPage() {
  const { t } = useTranslation();
  // En el servidor no hay fragmento: `null` hasta que la página corre en el navegador.
  const token = useSyncExternalStore(alCambiarElFragmento, tokenDelFragmento, () => null);
  const [accion, setAccion] = useState<Accion>({ tipo: "inicial" });

  async function abrir(valor: string) {
    setAccion({ tipo: "abriendo" });
    try {
      const dossier = await redeemDossierAccessLink(valor);
      // El token ya se gastó: no tiene sentido dejarlo en el historial del navegador.
      window.history.replaceState(null, "", window.location.pathname);
      setAccion({ tipo: "visto", dossier });
    } catch (e) {
      setAccion(e instanceof DossierApiError && e.status === 410 ? { tipo: "invalido" } : { tipo: "error" });
    }
  }

  if (accion.tipo === "visto") {
    const { dossier } = accion;
    return (
      <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-4 py-10">
        <header className="flex flex-col gap-1">
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            {t("access.title")}
          </p>
          <h1 className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
            {dossier.subject_name}
          </h1>
        </header>
        <article
          className="api-md max-w-none text-sm leading-relaxed"
          style={{ color: "var(--text-primary)" }}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{dossier.body}</ReactMarkdown>
        </article>
        <p className="text-xs" style={{ color: "var(--text-subtle)" }}>
          {t("access.used_note")}{" "}
          <Link href="/login" className="underline">
            {t("access.login")}
          </Link>
        </p>
      </main>
    );
  }

  return (
    <AuthShell title={t("access.title")} subtitle={t("access.subtitle")} footer={null}>
      {token === null ? null : !token || accion.tipo === "invalido" ? (
        <div className="flex flex-col gap-4 text-sm">
          <p role="alert" style={{ color: "var(--text-secondary)" }}>
            {t("access.invalid")}
          </p>
          <Link href="/login" className="font-semibold underline">
            {t("access.login")}
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {accion.tipo === "error" ? (
            <p role="alert" className="text-sm text-red-300/90">
              {t("access.error")}
            </p>
          ) : null}
          <PrimaryButton type="button" loading={accion.tipo === "abriendo"} onClick={() => void abrir(token)}>
            {t("access.open")}
          </PrimaryButton>
        </div>
      )}
    </AuthShell>
  );
}
