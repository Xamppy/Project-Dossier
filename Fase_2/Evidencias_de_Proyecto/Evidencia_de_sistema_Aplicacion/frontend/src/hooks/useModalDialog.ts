import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

type Options = {
  /** Con otro diálogo encima, este no atiende el teclado. */
  paused?: boolean;
  /** Elemento que recupera el foco al cerrarse. */
  restoreFocus: () => HTMLElement | null;
};

/** Foco al abrir, Escape y trampa de Tab; al desmontarse, el foco vuelve a `restoreFocus`. */
export function useModalDialog(
  dialogRef: RefObject<HTMLElement | null>,
  onClose: () => void,
  { paused = false, restoreFocus }: Options,
): void {
  const latest = useRef({ onClose, paused, restoreFocus });
  useEffect(() => {
    latest.current = { onClose, paused, restoreFocus };
  });

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.focus();

    function onKeyDown(e: KeyboardEvent) {
      if (latest.current.paused) return;
      if (e.key === "Escape") {
        e.stopPropagation();
        latest.current.onClose();
        return;
      }
      if (e.key !== "Tab" || !dialog) return;
      const items = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) {
        e.preventDefault();
        dialog.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (!dialog.contains(active) || active === dialog) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      } else if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      latest.current.restoreFocus()?.focus();
    };
  }, [dialogRef]);
}
