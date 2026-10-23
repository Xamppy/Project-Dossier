"use client";

export type FilterValue = "all" | "active" | "past" | "needs_update";

type FilterTabsProps = {
  tabs: { value: FilterValue; label: string; count: number }[];
  active: FilterValue;
  onChange: (value: FilterValue) => void;
};

export default function FilterTabs({ tabs, active, onChange }: FilterTabsProps) {
  return (
    <div
      className="inline-flex flex-wrap items-center gap-1 rounded-lg border p-1"
      style={{
        borderColor: "var(--border-default)",
        backgroundColor: "var(--bg-surface)",
      }}
    >
      {tabs.map((tab) => {
        const isActive = tab.value === active;
        return (
          <button
            key={tab.value}
            type="button"
            onClick={() => onChange(tab.value)}
            className={
              isActive
                ? "ui-filter-tab-btn ui-filter-tab-btn--active"
                : "ui-filter-tab-btn ui-filter-tab-btn--inactive"
            }
          >
            {tab.label}
            <span
              className="ml-1.5 text-xs"
              style={{ color: "var(--text-subtle)" }}
            >
              ({tab.count})
            </span>
          </button>
        );
      })}
    </div>
  );
}
