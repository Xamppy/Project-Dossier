type ToggleProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
};

export default function Toggle({
  checked,
  onChange,
  disabled,
  label,
}: ToggleProps) {
  return (
    <label className="inline-flex items-center gap-2 cursor-pointer">
      {label && (
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          {label}
        </span>
      )}
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className="relative h-6 w-11 rounded-full transition disabled:cursor-not-allowed disabled:opacity-50"
        style={{
          backgroundColor: checked ? "var(--accent-from)" : "var(--toggle-bg, #334155)",
        }}
      >
        <span
          className="absolute top-0.5 h-5 w-5 rounded-full bg-white transition"
          style={{ left: checked ? "1.375rem" : "0.125rem" }}
        />
      </button>
    </label>
  );
}
