"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import TopBar from "@/components/dashboard/TopBar";
import {
  DossierApiError,
  deleteAdminUser,
  fetchAdminDossiers,
  fetchAdminOrganizations,
  fetchAdminOverview,
  fetchAdminUsers,
  fetchAuthMe,
  patchAdminUserRoles,
  type AdminDossierRow,
  type AdminOrgRow,
  type AdminOverview,
  type AdminUserRow,
} from "@/lib/dossier-api";
import { useTranslation } from "@/providers/PreferencesProvider";
import type { TranslationKey } from "@/i18n/types";
import { formatDossierStatusLabel } from "@/lib/dossier-list-utils";

function fmtDate(iso: string | null, locale: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(locale.replace("_", "-"), {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function workspaceOrgLabel(
  t: (key: TranslationKey) => string,
  workspaceKind: "personal" | "work" | null | undefined,
  organizationName: string | null | undefined
): string {
  if (workspaceKind === "personal") return t("workspace.personal");
  const n = organizationName?.trim();
  return n && n !== "" ? n : "—";
}

type SectionKey = "users" | "orgs" | "dossiers";

function AdminAccordionPanel({
  title,
  summary,
  open,
  onToggle,
  children,
}: {
  title: string;
  summary: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="overflow-hidden rounded-xl border"
      style={{ borderColor: "var(--border-subtle)" }}
    >
      <button
        type="button"
        onClick={onToggle}
        title={`${title} — ${summary}`}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-white/5"
        style={{ backgroundColor: "var(--bg-surface)" }}
        aria-expanded={open}
      >
        <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
          {title}
        </span>
        <span className="flex shrink-0 items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
          <span className="hidden sm:inline">{summary}</span>
          <svg
            viewBox="0 0 24 24"
            width="20"
            height="20"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className={`shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
            aria-hidden
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </span>
      </button>
      {open ? (
        <div className="border-t px-2 pb-4 pt-2" style={{ borderColor: "var(--border-subtle)" }}>
          {children}
        </div>
      ) : null}
    </div>
  );
}

export default function AdminDashboardPage() {
  const { t, locale } = useTranslation();
  const router = useRouter();
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [orgs, setOrgs] = useState<AdminOrgRow[]>([]);
  const [dossiers, setDossiers] = useState<AdminDossierRow[]>([]);
  const [meId, setMeId] = useState<string | null>(null);
  const [savingUserId, setSavingUserId] = useState<string | null>(null);
  const [deletingUserId, setDeletingUserId] = useState<string | null>(null);
  const [openSection, setOpenSection] = useState<Record<SectionKey, boolean>>({
    users: false,
    orgs: false,
    dossiers: false,
  });

  const toggleSection = useCallback((key: SectionKey) => {
    setOpenSection((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      setError(null);
      try {
        const me = await fetchAuthMe();
        if (!me.is_platform_admin) {
          if (!cancelled) {
            setBlocked(true);
            router.replace("/dashboard");
          }
          return;
        }
        if (!cancelled) setMeId(me.id);
        const [ov, u, o, d] = await Promise.all([
          fetchAdminOverview(),
          fetchAdminUsers(100, 0),
          fetchAdminOrganizations(100, 0),
          fetchAdminDossiers(100, 0),
        ]);
        if (!cancelled) {
          setOverview(ov);
          setUsers(u.items);
          setOrgs(o.items);
          setDossiers(d.items);
        }
      } catch (e) {
        if (cancelled) return;
        if (e instanceof DossierApiError && (e.status === 403 || e.status === 401)) {
          setBlocked(true);
          router.replace("/dashboard");
          return;
        }
        setError(e instanceof DossierApiError ? e.message : t("admin.load_error"));
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [router, t]);

  async function handleDeleteUser(user: AdminUserRow) {
    if (meId !== null && user.id === meId) return;
    if (!window.confirm(t("admin.delete_confirm", { email: user.email }))) {
      return;
    }
    setDeletingUserId(user.id);
    setError(null);
    try {
      await deleteAdminUser(user.id);
      setUsers((prev) => prev.filter((x) => x.id !== user.id));
      setOverview((prev) =>
        prev ? { ...prev, users_total: Math.max(0, prev.users_total - 1) } : prev,
      );
    } catch (e) {
      setError(e instanceof DossierApiError ? e.message : t("admin.load_error"));
    } finally {
      setDeletingUserId(null);
    }
  }

  async function applyUserRoles(userId: string, body: { is_platform_admin: boolean }) {
    setSavingUserId(userId);
    setError(null);
    try {
      const updated = await patchAdminUserRoles(userId, body);
      setUsers((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
    } catch (e) {
      setError(e instanceof DossierApiError ? e.message : t("admin.load_error"));
    } finally {
      setSavingUserId(null);
    }
  }

  if (blocked && !overview) {
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-2 px-6">
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {t("admin.redirecting")}
        </p>
      </div>
    );
  }

  const usersSummary = overview
    ? t("admin.summary_users", { count: overview.users_total })
    : "";
  const orgsSummary = overview
    ? t("admin.summary_orgs", { count: overview.organizations_total })
    : "";
  const dossiersSummary = overview
    ? t("admin.summary_dossiers", { count: overview.dossiers_total })
    : "";

  return (
    <div className="flex flex-col gap-6 px-6 pb-10 pt-2 md:px-8">
      <TopBar title={t("admin.title")} subtitle={t("admin.subtitle")} />

      {error ? (
        <div
          className="rounded-lg border px-4 py-3 text-sm"
          style={{ borderColor: "var(--border-default)", color: "var(--accent-danger, #f87171)" }}
        >
          {error}
        </div>
      ) : null}

      {overview ? (
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            { label: t("admin.stat_users"), value: overview.users_total },
            { label: t("admin.stat_orgs"), value: overview.organizations_total },
            { label: t("admin.stat_dossiers"), value: overview.dossiers_total },
          ].map((card) => (
            <div
              key={card.label}
              className="rounded-xl border px-5 py-4"
              style={{
                borderColor: "var(--border-subtle)",
                backgroundColor: "var(--bg-surface)",
              }}
            >
              <p
                className="text-xs font-medium uppercase tracking-wide"
                style={{ color: "var(--text-muted)" }}
              >
                {card.label}
              </p>
              <p
                className="mt-1 text-2xl font-semibold tabular-nums"
                style={{ color: "var(--text-primary)" }}
              >
                {card.value}
              </p>
            </div>
          ))}
        </div>
      ) : null}

      <div className="flex flex-col gap-3">
        <AdminAccordionPanel
          title={t("admin.section_users")}
          summary={usersSummary}
          open={openSection.users}
          onToggle={() => toggleSection("users")}
        >
          <div className="overflow-x-auto rounded-lg border" style={{ borderColor: "var(--border-subtle)" }}>
            <table className="min-w-full text-left text-sm">
              <thead style={{ backgroundColor: "var(--bg-surface-strong)" }}>
                <tr>
                  <th
                    className="sticky left-0 z-10 px-3 py-2 font-medium"
                    style={{ backgroundColor: "var(--bg-surface-strong)" }}
                  >
                    {t("admin.col_actions")}
                  </th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_email")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_name")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_active")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.platform_role")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_org")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_plan")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_credits")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_limit")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_dossiers_user")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_created")}</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const busy = savingUserId === u.id || deletingUserId === u.id;
                  const isSelf = meId !== null && u.id === meId;
                  return (
                    <tr
                      key={u.id}
                      className="border-t"
                      style={{
                        borderColor: "var(--border-subtle)",
                        opacity: busy ? 0.65 : 1,
                      }}
                    >
                      <td
                        className="sticky left-0 z-10 px-3 py-2 whitespace-nowrap"
                        style={{ backgroundColor: "var(--bg-surface)" }}
                      >
                        {isSelf ? (
                          <span className="text-xs" style={{ color: "var(--text-subtle)" }}>
                            —
                          </span>
                        ) : (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void handleDeleteUser(u)}
                            className="rounded border border-red-500/40 px-2 py-1 text-xs font-medium text-red-300 transition hover:bg-red-500/10 disabled:opacity-50"
                          >
                            {deletingUserId === u.id
                              ? t("admin.deleting_user")
                              : t("admin.delete_user")}
                          </button>
                        )}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">{u.email}</td>
                      <td className="px-3 py-2">{u.full_name || "—"}</td>
                      <td className="px-3 py-2">{u.is_active ? "✓" : "—"}</td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        <select
                          className="max-w-[9rem] rounded border bg-transparent px-1 py-1 text-xs"
                          style={{ borderColor: "var(--border-default)" }}
                          value={u.is_platform_admin ? "1" : "0"}
                          disabled={busy}
                          onChange={(e) => {
                            const next = e.target.value === "1";
                            void applyUserRoles(u.id, { is_platform_admin: next });
                          }}
                          aria-label={t("admin.platform_role")}
                        >
                          <option value="0" disabled={isSelf && u.is_platform_admin}>
                            {t("admin.platform_no")}
                          </option>
                          <option value="1">{t("admin.platform_yes")}</option>
                        </select>
                      </td>
                      <td className="px-3 py-2">
                        {workspaceOrgLabel(t, u.workspace_kind, u.organization_name)}
                      </td>
                      <td className="px-3 py-2">{u.plan || "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{u.credits_balance ?? "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{u.credits_monthly_limit ?? "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{u.dossiers_count}</td>
                      <td className="px-3 py-2 whitespace-nowrap text-xs">
                        {fmtDate(u.created_at, locale)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </AdminAccordionPanel>

        <AdminAccordionPanel
          title={t("admin.section_orgs")}
          summary={orgsSummary}
          open={openSection.orgs}
          onToggle={() => toggleSection("orgs")}
        >
          <div className="overflow-x-auto rounded-lg border" style={{ borderColor: "var(--border-subtle)" }}>
            <table className="min-w-full text-left text-sm">
              <thead style={{ backgroundColor: "var(--bg-surface-strong)" }}>
                <tr>
                  <th className="px-3 py-2 font-medium">{t("admin.col_org")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_org_url")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_plan")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_credits")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_limit")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_members")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_dossiers_org")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_active")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_created")}</th>
                </tr>
              </thead>
              <tbody>
                {orgs.map((o) => (
                  <tr key={o.id} className="border-t" style={{ borderColor: "var(--border-subtle)" }}>
                    <td className="px-3 py-2">{workspaceOrgLabel(t, o.workspace_kind, o.name)}</td>
                    <td className="px-3 py-2 font-mono text-xs">{o.slug}</td>
                    <td className="px-3 py-2">{o.plan}</td>
                    <td className="px-3 py-2 tabular-nums">{o.credits_balance}</td>
                    <td className="px-3 py-2 tabular-nums">{o.credits_monthly_limit}</td>
                    <td className="px-3 py-2 tabular-nums">{o.members_count}</td>
                    <td className="px-3 py-2 tabular-nums">{o.dossiers_count}</td>
                    <td className="px-3 py-2">{o.is_active ? "✓" : "—"}</td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs">{fmtDate(o.created_at, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AdminAccordionPanel>

        <AdminAccordionPanel
          title={t("admin.section_dossiers")}
          summary={dossiersSummary}
          open={openSection.dossiers}
          onToggle={() => toggleSection("dossiers")}
        >
          <div className="overflow-x-auto rounded-lg border" style={{ borderColor: "var(--border-subtle)" }}>
            <table className="min-w-full text-left text-sm">
              <thead style={{ backgroundColor: "var(--bg-surface-strong)" }}>
                <tr>
                  <th className="px-3 py-2 font-medium">{t("admin.col_date")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_org")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_requested_by")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_subject")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_status")}</th>
                  <th className="px-3 py-2 font-medium">{t("admin.col_credits_used")}</th>
                </tr>
              </thead>
              <tbody>
                {dossiers.map((d) => (
                  <tr key={d.id} className="border-t" style={{ borderColor: "var(--border-subtle)" }}>
                    <td className="px-3 py-2 whitespace-nowrap text-xs">{fmtDate(d.created_at, locale)}</td>
                    <td className="px-3 py-2">
                      {workspaceOrgLabel(t, d.workspace_kind, d.organization_name)}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{d.requested_by_email}</td>
                    <td className="px-3 py-2">{d.subject_name || d.subject_email || "—"}</td>
                    <td className="px-3 py-2">{formatDossierStatusLabel(d.status, t)}</td>
                    <td className="px-3 py-2 tabular-nums">{d.credits_consumed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AdminAccordionPanel>
      </div>
    </div>
  );
}
