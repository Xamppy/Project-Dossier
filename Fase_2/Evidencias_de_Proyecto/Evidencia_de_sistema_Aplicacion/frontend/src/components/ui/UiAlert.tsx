import type { HTMLAttributes, ReactNode } from "react";

type UiAlertVariant = "warning" | "success" | "error" | "info";

type UiAlertProps = HTMLAttributes<HTMLDivElement> & {
  variant?: UiAlertVariant;
  children: ReactNode;
};

export default function UiAlert({
  variant = "warning",
  children,
  className = "",
  ...rest
}: UiAlertProps) {
  return (
    <div
      className={`ui-alert ui-alert-${variant} rounded-lg border px-3 py-2 text-sm ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
