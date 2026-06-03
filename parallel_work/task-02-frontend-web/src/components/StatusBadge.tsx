import { cn } from "../lib/format";

type Tone =
  | "healthy"
  | "degraded"
  | "offline"
  | "online"
  | "idle"
  | "warning"
  | "starting"
  | "success"
  | "critical"
  | "info";

interface StatusBadgeProps {
  label: string;
  tone: Tone;
  compact?: boolean;
}

export function StatusBadge({ label, tone, compact = false }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "status-badge",
        `status-badge--${tone}`,
        compact && "status-badge--compact",
      )}
    >
      {label}
    </span>
  );
}
