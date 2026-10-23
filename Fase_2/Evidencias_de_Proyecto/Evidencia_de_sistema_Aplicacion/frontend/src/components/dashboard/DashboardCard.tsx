import type { ReactNode } from "react";

type DashboardCardProps = {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
};

export default function DashboardCard({
  title,
  action,
  children,
  className = "",
}: DashboardCardProps) {
  return (
    <div
      className={`rounded-xl border p-6 ${className}`}
      style={{
        borderColor: "var(--border-default)",
        backgroundImage:
          "linear-gradient(180deg, var(--bg-card-start) 0%, var(--bg-card-end) 100%)",
      }}
    >
      {(title || action) && (
        <div className="mb-5 flex items-center justify-between">
          {title && (
            <h3
              className="text-base font-semibold"
              style={{ color: "var(--text-primary)" }}
            >
              {title}
            </h3>
          )}
          {action}
        </div>
      )}
      {children}
    </div>
  );
}
