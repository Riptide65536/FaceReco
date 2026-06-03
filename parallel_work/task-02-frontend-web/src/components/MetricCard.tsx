interface MetricCardProps {
  label: string;
  value: string;
  helper: string;
  tone?: "default" | "accent" | "warning";
}

export function MetricCard({
  label,
  value,
  helper,
  tone = "default",
}: MetricCardProps) {
  return (
    <article className={`metric-card metric-card--${tone}`}>
      <p className="metric-card__label">{label}</p>
      <p className="metric-card__value">{value}</p>
      <p className="metric-card__helper">{helper}</p>
    </article>
  );
}
