"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import DashboardCard from "@/components/dashboard/DashboardCard";
import FormField from "@/components/FormField";
import PrimaryButton from "@/components/PrimaryButton";
import {
  clearAuthSession,
  deleteMyAccount,
  DossierApiError,
  fetchAuthMe,
  getAuthTokenStorageMode,
  getStoredAccessToken,
  patchMyEmail,
  patchMyPassword,
  persistAuthToken,
  writeDossierUserPreview,
} from "@/lib/dossier-api";
import { translateApiErrorMessage } from "@/lib/translate-backend-message";
import { useTranslation } from "@/providers/PreferencesProvider";

export default function AccountPanel() {
  const { t } = useTranslation();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [emailMsg, setEmailMsg] = useState("");
  const [emailErr, setEmailErr] = useState("");
  const [passwordMsg, setPasswordMsg] = useState("");
  const [passwordErr, setPasswordErr] = useState("");
  const [deleteErr, setDeleteErr] = useState("");
  const [savingEmail, setSavingEmail] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!getStoredAccessToken()) return;
    void fetchAuthMe()
      .then((me) => {
        setEmail(me.email);
        setNewEmail(me.email);
      })
      .catch(() => {
        /* ignore */
      });
  }, []);

  async function handleChangeEmail(e: React.FormEvent) {
    e.preventDefault();
    setEmailErr("");
    setEmailMsg("");
    if (!newEmail.trim()) {
      setEmailErr(t("settings.account.error_email_required"));
      return;
    }
    setSavingEmail(true);
    try {
      const data = await patchMyEmail({
        new_email: newEmail.trim(),
        current_password: emailPassword,
      });
      const remember = getAuthTokenStorageMode() === "local";
      persistAuthToken(data.access_token, remember);
      writeDossierUserPreview(
        {
          email: data.user.email,
          full_name: data.user.full_name,
          company_name: data.user.company_name,
          workspace_kind: data.user.workspace_kind,
          organization_plan: data.user.organization_plan,
          is_platform_admin: data.user.is_platform_admin,
        },
        remember ? "local" : "session",
      );
      setEmail(data.user.email);
      setNewEmail(data.user.email);
      setEmailPassword("");
      setEmailMsg(t("settings.account.success_email"));
    } catch (err) {
      setEmailErr(
        err instanceof DossierApiError
          ? translateApiErrorMessage(err, t)
          : t("errors.server_generic"),
      );
    } finally {
      setSavingEmail(false);
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setPasswordErr("");
    setPasswordMsg("");
    if (newPassword.length < 8) {
      setPasswordErr(t("settings.account.error_password_short"));
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordErr(t("settings.account.error_password_mismatch"));
      return;
    }
    setSavingPassword(true);
    try {
      await patchMyPassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordMsg(t("settings.account.success_password"));
    } catch (err) {
      setPasswordErr(
        err instanceof DossierApiError
          ? translateApiErrorMessage(err, t)
          : t("errors.server_generic"),
      );
    } finally {
      setSavingPassword(false);
    }
  }

  async function handleDeleteAccount() {
    setDeleteErr("");
    if (deleteConfirm.trim().toUpperCase() !== "DELETE") {
      setDeleteErr(t("settings.account.error_delete_confirm"));
      return;
    }
    if (!window.confirm(t("settings.account.delete_confirm"))) {
      return;
    }
    setDeleting(true);
    try {
      await deleteMyAccount({
        current_password: deletePassword,
        confirm: "DELETE",
      });
      clearAuthSession();
      router.push("/login");
      router.refresh();
    } catch (err) {
      setDeleteErr(
        err instanceof DossierApiError
          ? translateApiErrorMessage(err, t)
          : t("errors.server_generic"),
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <DashboardCard title={t("settings.account.title")}>
        <p className="mb-6 text-sm" style={{ color: "var(--text-muted)" }}>
          {t("settings.account.subtitle")}
        </p>

        <form onSubmit={(e) => void handleChangeEmail(e)} className="flex flex-col gap-4">
          <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            {t("settings.account.email_section")}
          </h3>
          <FormField
            label={t("settings.account.email_current")}
            type="email"
            name="current_email"
            value={email}
            readOnly
          />
          <FormField
            label={t("settings.account.email_new")}
            type="email"
            name="new_email"
            autoComplete="email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            required
          />
          <FormField
            label={t("settings.account.password_current")}
            type="password"
            name="email_password"
            autoComplete="current-password"
            value={emailPassword}
            onChange={(e) => setEmailPassword(e.target.value)}
            passwordToggle
            required
          />
          {emailMsg ? (
            <p className="text-sm text-emerald-400" role="status">
              {emailMsg}
            </p>
          ) : null}
          {emailErr ? (
            <p className="text-sm text-red-400" role="alert">
              {emailErr}
            </p>
          ) : null}
          <div>
            <PrimaryButton type="submit" disabled={savingEmail}>
              {savingEmail ? t("settings.account.saving") : t("settings.account.change_email")}
            </PrimaryButton>
          </div>
        </form>

        <hr className="my-8" style={{ borderColor: "var(--border-default)" }} />

        <form onSubmit={(e) => void handleChangePassword(e)} className="flex flex-col gap-4">
          <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            {t("settings.account.password_section")}
          </h3>
          <FormField
            label={t("settings.account.password_current")}
            type="password"
            name="current_password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            passwordToggle
            required
          />
          <FormField
            label={t("settings.account.password_new")}
            type="password"
            name="new_password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            passwordToggle
            minLength={8}
            required
          />
          <FormField
            label={t("settings.account.password_confirm")}
            type="password"
            name="confirm_password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            passwordToggle
            minLength={8}
            required
          />
          {passwordMsg ? (
            <p className="text-sm text-emerald-400" role="status">
              {passwordMsg}
            </p>
          ) : null}
          {passwordErr ? (
            <p className="text-sm text-red-400" role="alert">
              {passwordErr}
            </p>
          ) : null}
          <div>
            <PrimaryButton type="submit" disabled={savingPassword}>
              {savingPassword
                ? t("settings.account.saving")
                : t("settings.account.change_password")}
            </PrimaryButton>
          </div>
        </form>
      </DashboardCard>

      <DashboardCard title={t("settings.account.delete_title")}>
        <p className="mb-4 text-sm" style={{ color: "var(--text-muted)" }}>
          {t("settings.account.delete_desc")}
        </p>
        <div className="flex flex-col gap-4">
          <FormField
            label={t("settings.account.password_current")}
            type="password"
            name="delete_password"
            autoComplete="current-password"
            value={deletePassword}
            onChange={(e) => setDeletePassword(e.target.value)}
            passwordToggle
          />
          <FormField
            label={t("settings.account.delete_type_confirm")}
            type="text"
            name="delete_confirm"
            value={deleteConfirm}
            onChange={(e) => setDeleteConfirm(e.target.value)}
            placeholder="DELETE"
            autoComplete="off"
          />
          {deleteErr ? (
            <p className="text-sm text-red-400" role="alert">
              {deleteErr}
            </p>
          ) : null}
          <div>
            <button
              type="button"
              disabled={deleting}
              onClick={() => void handleDeleteAccount()}
              className="rounded-lg border border-red-500/50 bg-red-500/10 px-4 py-2.5 text-sm font-semibold text-red-300 transition hover:bg-red-500/20 disabled:opacity-50"
            >
              {deleting ? t("settings.account.deleting") : t("settings.account.delete_button")}
            </button>
          </div>
        </div>
      </DashboardCard>
    </div>
  );
}
