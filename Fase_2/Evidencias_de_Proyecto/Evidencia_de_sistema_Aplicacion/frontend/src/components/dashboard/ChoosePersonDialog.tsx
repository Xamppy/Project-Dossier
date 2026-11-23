"use client";

import { useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useModalDialog } from "@/hooks/useModalDialog";
import type { CalendarUiLabels } from "@/i18n/calendar-ui-labels";
import type { CalendarPerson } from "@/lib/dossier-api";

type Props = {
  people: CalendarPerson[];
  /** Motivo por el que hay que elegir otra vez. */
  notice: string | null;
  labels: CalendarUiLabels;
  onCancel: () => void;
  onConfirm: (personId: string) => void;
  restoreFocus: () => HTMLElement | null;
};

/** Elección de la única persona de la reunión cuyo dossier se genera (UX-CAL-03). */
export default function ChoosePersonDialog({ people, notice, labels, onCancel, onConfirm, restoreFocus }: Props) {
  const titleId = useId();
  const helpId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useModalDialog(dialogRef, onCancel, { restoreFocus });

  // Fuera del detalle: dentro de él, los avisos flotantes de otros dossiers taparían los botones.
  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div
        className="absolute inset-0"
        style={{ backgroundColor: "rgba(4, 10, 22, 0.6)" }}
        onClick={onCancel}
        aria-hidden
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={helpId}
        tabIndex={-1}
        className="relative flex max-h-[85vh] w-full max-w-md flex-col rounded-2xl border p-5 shadow-2xl outline-none"
        style={{ backgroundColor: "var(--bg-page)", borderColor: "var(--border-default)" }}
      >
        <h2 id={titleId} className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
          {labels.choosePersonTitle}
        </h2>
        <p id={helpId} className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
          {labels.choosePersonHelp}
        </p>
        {notice ? (
          <p className="ui-alert ui-alert-error mt-3 px-2.5 py-2 text-xs" role="alert">{notice}</p>
        ) : null}

        <ul className="mt-4 min-h-0 flex-1 space-y-2 overflow-y-auto">
          {people.map((p) => {
            const checked = selected === p.id;
            return (
              <li key={p.id}>
                <label
                  className="flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5"
                  style={{
                    borderColor: checked ? "var(--accent-from)" : "var(--border-default)",
                    backgroundColor: "var(--bg-input)",
                  }}
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 shrink-0"
                    style={{ accentColor: "var(--accent-from)" }}
                    checked={checked}
                    onChange={() => setSelected(checked ? null : p.id)}
                  />
                  <span className="min-w-0">
                    <span className="block break-words text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                      {p.cargo ? `${p.nombre} · ${p.cargo}` : p.nombre}
                    </span>
                    {p.correo ? (
                      <span className="block break-all text-xs" style={{ color: "var(--text-secondary)" }}>
                        {p.correo}
                      </span>
                    ) : null}
                  </span>
                </label>
              </li>
            );
          })}
        </ul>

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border px-3.5 py-2 text-sm font-medium"
            style={{ borderColor: "var(--border-default)", color: "var(--text-primary)" }}
          >
            {labels.choosePersonCancel}
          </button>
          <button
            type="button"
            disabled={selected === null}
            onClick={() => selected !== null && onConfirm(selected)}
            className="rounded-lg px-3.5 py-2 text-sm font-semibold text-white transition hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-50"
            style={{ backgroundImage: "linear-gradient(135deg, var(--accent-from) 0%, var(--accent-to) 100%)" }}
          >
            {labels.choosePersonConfirm}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
