type ThemePreviewVariant = "dark" | "light" | "system";

type ThemePreviewProps = {
  variant: ThemePreviewVariant;
};

function MiniUiMock({ mode }: { mode: "dark" | "light" }) {
  const isDark = mode === "dark";

  return (
    <div
      className="flex h-full w-full overflow-hidden rounded-md"
      style={{
        background: isDark
          ? "linear-gradient(160deg, #0f1f3d 0%, #0a1428 100%)"
          : "linear-gradient(160deg, #f4f8fc 0%, #e8f0f8 100%)",
        border: isDark
          ? "1px solid rgba(148, 163, 184, 0.25)"
          : "1px solid rgba(15, 23, 42, 0.12)",
      }}
    >
      {/* Sidebar */}
      <div
        className="flex w-[28%] flex-col gap-1 p-1.5"
        style={{
          backgroundColor: isDark ? "rgba(15, 23, 42, 0.85)" : "rgba(255, 255, 255, 0.9)",
          borderRight: isDark
            ? "1px solid rgba(148, 163, 184, 0.15)"
            : "1px solid rgba(15, 23, 42, 0.08)",
        }}
      >
        <div
          className="h-1.5 w-3/4 rounded-full"
          style={{
            background: "linear-gradient(90deg, #00b7eb, #1e90ff)",
          }}
        />
        <div
          className="mt-1 h-1 w-full rounded-full"
          style={{
            backgroundColor: isDark ? "rgba(148, 163, 184, 0.35)" : "rgba(15, 23, 42, 0.12)",
          }}
        />
        <div
          className="h-1 w-4/5 rounded-full"
          style={{
            backgroundColor: isDark ? "rgba(148, 163, 184, 0.22)" : "rgba(15, 23, 42, 0.08)",
          }}
        />
        <div
          className="h-1 w-3/5 rounded-full"
          style={{
            backgroundColor: isDark ? "rgba(148, 163, 184, 0.22)" : "rgba(15, 23, 42, 0.08)",
          }}
        />
      </div>

      {/* Content */}
      <div className="flex flex-1 flex-col gap-1 p-1.5">
        <div
          className="h-1.5 w-2/5 rounded-full"
          style={{
            backgroundColor: isDark ? "rgba(226, 232, 240, 0.55)" : "rgba(15, 23, 42, 0.35)",
          }}
        />
        <div className="mt-0.5 grid flex-1 grid-cols-2 gap-1">
          <div
            className="rounded-sm"
            style={{
              backgroundColor: isDark ? "rgba(51, 65, 85, 0.7)" : "rgba(255, 255, 255, 0.95)",
              border: isDark
                ? "1px solid rgba(148, 163, 184, 0.12)"
                : "1px solid rgba(15, 23, 42, 0.06)",
            }}
          />
          <div
            className="rounded-sm"
            style={{
              backgroundColor: isDark ? "rgba(51, 65, 85, 0.7)" : "rgba(255, 255, 255, 0.95)",
              border: isDark
                ? "1px solid rgba(148, 163, 184, 0.12)"
                : "1px solid rgba(15, 23, 42, 0.06)",
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default function ThemePreview({ variant }: ThemePreviewProps) {
  if (variant === "system") {
    return (
      <div
        className="relative h-16 w-full overflow-hidden rounded-lg"
        style={{ border: "1px solid rgba(148, 163, 184, 0.25)" }}
      >
        <div className="absolute inset-0 flex">
          <div className="w-1/2 overflow-hidden p-0.5">
            <MiniUiMock mode="dark" />
          </div>
          <div className="w-1/2 overflow-hidden p-0.5">
            <MiniUiMock mode="light" />
          </div>
        </div>
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "linear-gradient(135deg, transparent 48%, rgba(0, 183, 235, 0.35) 50%, transparent 52%)",
          }}
        />
      </div>
    );
  }

  return (
    <div className="h-16 w-full">
      <MiniUiMock mode={variant} />
    </div>
  );
}
