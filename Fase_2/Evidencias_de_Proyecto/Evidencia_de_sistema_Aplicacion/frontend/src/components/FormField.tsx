"use client";

import { useState, type InputHTMLAttributes } from "react";
import { useTranslation } from "@/providers/PreferencesProvider";

type FormFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
  hint?: string;
  /** Muestra un botón con icono para alternar visibilidad (solo con `type="password"`). */
  passwordToggle?: boolean;
};

function EyeIcon({ open }: { open: boolean }) {
  if (open) {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5" aria-hidden>
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5" aria-hidden>
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}

export default function FormField({
  label,
  error,
  hint,
  id,
  passwordToggle,
  type,
  className,
  ...inputProps
}: FormFieldProps) {
  const { t } = useTranslation();
  const [passwordVisible, setPasswordVisible] = useState(false);
  const inputId = id ?? inputProps.name;
  const showToggle = Boolean(passwordToggle && type === "password");
  const inputType = showToggle && passwordVisible ? "text" : type;

  const inputClassName = [
    "w-full rounded-lg border py-2.5 text-sm outline-none transition focus:ring-2",
    showToggle ? "pl-3.5 pr-11" : "px-3.5",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  const inputEl = (
    <input
      id={inputId}
      type={inputType}
      {...inputProps}
      className={inputClassName}
      style={{
        backgroundColor: "var(--bg-input)",
        borderColor: error ? "#ef4444" : "var(--border-default)",
        color: "var(--text-primary)",
      }}
    />
  );

  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={inputId}
        className="text-sm font-medium"
        style={{ color: "var(--text-secondary)" }}
      >
        {label}
      </label>
      {showToggle ? (
        <div className="relative">
          {inputEl}
          <button
            type="button"
            className="absolute right-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md transition hover:opacity-90"
            style={{ color: "var(--text-muted)" }}
            aria-label={passwordVisible ? t("auth.password_hide") : t("auth.password_show")}
            aria-pressed={passwordVisible}
            onClick={() => setPasswordVisible((v) => !v)}
          >
            <EyeIcon open={passwordVisible} />
          </button>
        </div>
      ) : (
        inputEl
      )}
      {error ? (
        <span className="text-xs text-red-400">{error}</span>
      ) : hint ? (
        <span className="text-xs" style={{ color: "var(--text-subtle)" }}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}
