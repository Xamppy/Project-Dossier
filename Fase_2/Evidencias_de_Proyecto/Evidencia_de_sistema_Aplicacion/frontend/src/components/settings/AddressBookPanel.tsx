"use client";

import { useState } from "react";
import DashboardCard from "@/components/dashboard/DashboardCard";
import { useTranslation } from "@/providers/PreferencesProvider";
import type { TranslationKey } from "@/i18n/types";
import type { ContactGroup } from "@/lib/addressbook-types";

const GROUP_NAME_KEYS: Record<string, TranslationKey> = {
  vip: "group.vip",
  board: "group.board",
  prospects: "group.prospects",
  partners: "group.partners",
};

const IMPORT_OPTIONS: { labelKey: TranslationKey; icon: string }[] = [
  { labelKey: "addressbook.import_google", icon: "G" },
  { labelKey: "addressbook.import_outlook", icon: "O" },
  { labelKey: "addressbook.import_csv", icon: "CSV" },
];

export default function AddressBookPanel() {
  const { t } = useTranslation();
  const [groups, setGroups] = useState<ContactGroup[]>([]);
  const [newGroupName, setNewGroupName] = useState("");

  function groupLabel(group: ContactGroup): string {
    const key = GROUP_NAME_KEYS[group.id];
    return key ? t(key) : group.name;
  }

  function addGroup() {
    const name = newGroupName.trim();
    if (!name) return;
    setGroups((prev) => [
      ...prev,
      {
        id: name.toLowerCase().replace(/\s+/g, "-"),
        name,
        contactCount: 0,
      },
    ]);
    setNewGroupName("");
  }

  return (
    <DashboardCard title={t("settings.addressbook_title")}>
      <p className="mb-4 text-sm" style={{ color: "var(--text-muted)" }}>
        {t("settings.addressbook_desc")}
      </p>

      <div className="mb-6 flex gap-2">
        <input
          type="text"
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addGroup())}
          placeholder={t("addressbook.group_placeholder")}
          className="flex-1 rounded-lg border px-3 py-2 text-sm outline-none"
          style={{
            backgroundColor: "var(--bg-input)",
            borderColor: "var(--border-default)",
            color: "var(--text-primary)",
          }}
        />
        <button
          type="button"
          onClick={addGroup}
          className="rounded-lg px-4 py-2 text-sm font-semibold text-white transition hover:opacity-95"
          style={{
            backgroundImage:
              "linear-gradient(135deg, var(--accent-from) 0%, var(--accent-to) 100%)",
          }}
        >
          {t("addressbook.add_group")}
        </button>
      </div>

      {groups.length === 0 ? (
        <p className="mb-6 text-sm" style={{ color: "var(--text-muted)" }}>
          {t("addressbook.groups_empty")}
        </p>
      ) : (
        <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {groups.map((group) => (
            <div
              key={group.id}
              className="flex items-center gap-3 rounded-xl border p-4 transition hover:opacity-95"
              style={{
                borderColor: "var(--border-default)",
                backgroundColor: "var(--bg-surface)",
              }}
            >
              <div
                className="flex h-10 w-10 items-center justify-center rounded-lg"
                style={{
                  backgroundColor: "var(--bg-surface-strong)",
                  color: "var(--accent-from)",
                }}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              </div>
              <div className="flex flex-col">
                <span
                  className="text-sm font-semibold"
                  style={{ color: "var(--text-primary)" }}
                >
                  {groupLabel(group)}
                </span>
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {t("addressbook.contacts_count", { count: group.contactCount })}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      <h4
        className="mb-3 text-sm font-semibold"
        style={{ color: "var(--text-primary)" }}
      >
        {t("addressbook.import")}
      </h4>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {IMPORT_OPTIONS.map((opt) => (
          <button
            key={opt.labelKey}
            type="button"
            className="flex items-center gap-2 rounded-lg border px-3 py-3 text-sm font-medium transition hover:opacity-95"
            style={{
              borderColor: "var(--border-default)",
              backgroundColor: "var(--bg-surface)",
              color: "var(--text-primary)",
            }}
          >
            <span
              className="flex h-8 w-8 items-center justify-center rounded-md text-xs font-bold text-white"
              style={{
                backgroundImage:
                  "linear-gradient(135deg, var(--accent-from) 0%, var(--accent-to) 100%)",
              }}
            >
              {opt.icon}
            </span>
            {t(opt.labelKey)}
          </button>
        ))}
      </div>
    </DashboardCard>
  );
}
