import { useId, type ReactNode } from "react";

/** Tarjeta de una sección del dossier: misma apariencia que `DashboardCard`, como región con nombre. */
export function ModuleCard({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children?: ReactNode;
}) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className="rounded-xl border p-6"
      style={{
        borderColor: "var(--border-default)",
        backgroundImage: "linear-gradient(180deg, var(--bg-card-start) 0%, var(--bg-card-end) 100%)",
      }}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 id={headingId} className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
          {title}
        </h3>
        {action}
      </div>
      {children}
    </section>
  );
}

/** Enlace externo seguro: pestaña nueva y sin acceso a la página de origen. */
export function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-xs font-medium underline"
      style={{ color: "var(--accent-from)" }}
    >
      {children}
    </a>
  );
}

/** Fecha corta en el idioma del usuario. Las fechas sin hora no se desplazan de día. */
export function formatDay(value: string | null, locale: string): string | null {
  if (!value) return null;
  // ISO 8601 o la fecha compacta de GDELT (20261103T193800Z) de dossiers guardados antes del arreglo.
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value) ?? /^(\d{4})(\d{2})(\d{2})T\d{6}Z?$/.exec(value);
  if (!match) return value;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  if (Number.isNaN(date.getTime())) return value;
  try {
    return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone: "UTC" }).format(date);
  } catch {
    return value;
  }
}
