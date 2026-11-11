"use client";

import { useId } from "react";
import { countryName, groupRecordsByCountry, type CorporateRecordCitationApi } from "@/lib/dossier-modules";
import { useTranslation } from "@/providers/PreferencesProvider";
import { ExternalLink, ModuleCard, formatDay } from "./ModuleCard";

/** S3.5: registros mercantiles oficiales que coinciden con la empresa, agrupados por país. */
export function CorporateRecordsSection({ records }: { records: CorporateRecordCitationApi[] }) {
  const { t, locale } = useTranslation();
  if (records.length === 0) return null;
  return (
    <ModuleCard title={t("dossier_modules.corporate_records")}>
      <p className="mb-4 text-xs" style={{ color: "var(--text-muted)" }}>
        {t("dossier_modules.corporate_records_hint")}
      </p>
      <div className="flex flex-col gap-5">
        {groupRecordsByCountry(records).map((group) => (
          <CountryGroup key={group.country} name={countryName(group.country, locale)} records={group.records} />
        ))}
      </div>
    </ModuleCard>
  );
}

function CountryGroup({ name, records }: { name: string; records: CorporateRecordCitationApi[] }) {
  const labelId = useId();
  return (
    <div role="group" aria-labelledby={labelId}>
      <h4 id={labelId} className="mb-2 text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
        {name}
      </h4>
      <ul className="flex flex-col gap-3">
        {records.map((r, i) => (
          <RecordItem key={`${r.record.identificador_registro}-${i}`} item={r} />
        ))}
      </ul>
    </div>
  );
}

function RecordItem({ item }: { item: CorporateRecordCitationApi }) {
  const { t, locale } = useTranslation();
  const r = item.record;
  const address = r.domicilio
    ? [r.domicilio.calle, r.domicilio.codigo_postal, r.domicilio.localidad, r.domicilio.pais].filter(Boolean).join(", ")
    : "";
  const officers = r.directivos.slice(0, 5).map((d) => (d.cargo ? `${d.nombre} (${d.cargo})` : d.nombre));
  const consulted = formatDay(r.consultado_en ?? item.source?.retrieved_at ?? null, locale);
  const href = r.url_fuente ?? item.source?.url ?? null;
  const rows: [string, string | null][] = [
    [t("dossier_modules.record_id"), r.identificador_registro || null],
    [t("dossier_modules.status"), r.estado],
    [t("dossier_modules.legal_form"), r.forma_juridica],
    [t("dossier_modules.incorporated"), formatDay(r.fecha_constitucion, locale)],
    [t("dossier_modules.address"), address || null],
    [t("dossier_modules.officers"), officers.length ? officers.join(", ") : null],
  ];
  return (
    <li className="rounded-lg border p-3" style={{ borderColor: "var(--border-default)" }}>
      <p className="text-sm font-semibold break-words" style={{ color: "var(--text-primary)" }}>
        {r.razon_social}
      </p>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-[auto_1fr]">
        {rows
          .filter((row): row is [string, string] => Boolean(row[1]))
          .map(([label, value]) => (
            <div key={label} className="contents">
              <dt style={{ color: "var(--text-muted)" }}>{label}</dt>
              <dd className="break-words" style={{ color: "var(--text-secondary)" }}>
                {value}
              </dd>
            </div>
          ))}
      </dl>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs" style={{ color: "var(--text-muted)" }}>
        {item.source ? <span>{t("dossier_modules.source", { name: item.source.source_name })}</span> : null}
        {consulted ? <span>{t("dossier_modules.consulted", { date: consulted })}</span> : null}
        {href ? <ExternalLink href={href}>{t("dossier_modules.view_registry")}</ExternalLink> : null}
      </div>
    </li>
  );
}
