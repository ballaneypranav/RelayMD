interface MetricStripProps {
  items: Array<{
    label: string;
    value: number;
    tone?: "default" | "accent" | "danger" | "success";
  }>;
  ariaLabel?: string;
}

export function MetricStrip({ items, ariaLabel = "System overview" }: MetricStripProps) {
  return (
    <section className="metric-strip" aria-label={ariaLabel}>
      {items.map((item) => (
        <article className={`metric-tile tone-${item.tone ?? "default"}`} key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </article>
      ))}
    </section>
  );
}
