"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import AuthShell from "@/components/AuthShell";
import FormField from "@/components/FormField";
import PrimaryButton from "@/components/PrimaryButton";
import { authForgotPassword, DossierApiError } from "@/lib/dossier-api";
import { useTranslation } from "@/providers/PreferencesProvider";

type Errors = {
  email?: string;
};

export default function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  function validate(): Errors {
    const next: Errors = {};
    if (!email.trim()) {
      next.email = t("auth.error.email_required");
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      next.email = t("auth.error.email_invalid");
    }
    return next;
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const v = validate();
    setErrors(v);
    setFormError(null);
    if (Object.keys(v).length > 0) return;

    setLoading(true);
    try {
      await authForgotPassword({ email: email.trim() });
      setSuccess(true);
    } catch (e) {
      if (e instanceof DossierApiError) {
        if (e.isNetworkError()) setFormError(t("auth.forgot.error_network"));
        else setFormError(e.message || t("auth.forgot.error_server"));
      } else {
        setFormError(t("auth.forgot.error_server"));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell
      title={t("auth.forgot.title")}
      subtitle={t("auth.forgot.subtitle")}
      footer={
        <>
          {t("auth.forgot.footer_prompt")}{" "}
          <Link
            href="/login"
            className="font-semibold"
            style={{ color: "var(--accent-from)" }}
          >
            {t("auth.forgot.back_to_login")}
          </Link>
        </>
      }
    >
      {success ? (
        <div className="flex flex-col gap-4">
          <p
            className="rounded-lg border px-3 py-3 text-sm leading-relaxed"
            style={{
              borderColor: "var(--border-default)",
              backgroundColor: "var(--bg-surface)",
              color: "var(--text-muted)",
            }}
            role="status"
          >
            {t("auth.forgot.success_body")}
          </p>
          <Link
            href="/login"
            className="inline-flex justify-center rounded-lg px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90"
            style={{
              backgroundImage:
                "linear-gradient(135deg, var(--accent-from) 0%, var(--accent-to) 100%)",
            }}
          >
            {t("auth.forgot.back_to_login")}
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
          {formError && (
            <p
              className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200"
              role="alert"
            >
              {formError}
            </p>
          )}
          <FormField
            label={t("auth.login.email")}
            name="email"
            type="email"
            placeholder="tu@empresa.com"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={errors.email}
          />
          <PrimaryButton type="submit" loading={loading}>
            {t("auth.forgot.submit")}
          </PrimaryButton>
        </form>
      )}
    </AuthShell>
  );
}
