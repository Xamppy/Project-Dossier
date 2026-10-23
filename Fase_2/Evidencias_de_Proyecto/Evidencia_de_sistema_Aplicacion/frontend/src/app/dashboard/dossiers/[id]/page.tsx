"use client";

import Link from "next/link";
import { notFound, useParams } from "next/navigation";
import { useEffect, useState } from "react";
import CorporateDossierDetailView from "./CorporateDossierDetailView";
import { fetchDossierById, type DossierDetailResponse } from "@/lib/dossier-api";
import { useTranslation } from "@/providers/PreferencesProvider";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function PostgresDossierDetail({ id }: { id: string }) {
  const { t } = useTranslation();
  const [apiDossier, setApiDossier] = useState<DossierDetailResponse | null>(null);
  const [apiState, setApiState] = useState<"loading" | "ok" | "err">("loading");

  useEffect(() => {
    let cancelled = false;
    void fetchDossierById(id)
      .then((d) => {
        if (cancelled) return;
        setApiDossier(d);
        setApiState("ok");
      })
      .catch(() => {
        if (cancelled) return;
        setApiDossier(null);
        setApiState("err");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (apiState === "loading") {
    return (
      <div className="p-8 text-sm" style={{ color: "var(--text-muted)" }}>
        {t("detail.loading_dossier")}
      </div>
    );
  }

  if (apiState === "err" || !apiDossier) {
    return (
      <div className="mx-auto max-w-lg space-y-4 p-8">
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {t("detail.load_dossier_error")}
        </p>
        <Link
          href="/dashboard/dossiers"
          className="text-sm font-medium underline"
          style={{ color: "var(--accent-from)" }}
        >
          {t("detail.back_to_list")}
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <CorporateDossierDetailView dossier={apiDossier} />
    </div>
  );
}

export default function DossierDetailPage() {
  const params = useParams();
  const id = typeof params?.id === "string" ? params.id : "";
  const isUuid = Boolean(id && UUID_RE.test(id));

  if (!id || !isUuid) {
    notFound();
  }

  return <PostgresDossierDetail key={id} id={id} />;
}
