interface MetricStripProps {
  items: Array<{
    label: string;
    value: number;
    tone?: "default" | "accent" | "danger" | "success";
  }>;
}

export function MetricStrip({ items }: MetricStripProps) {
  return (
    <section className="metric-strip" aria-label="System overview">
      {items.map((item) => (
        <article className={`metric-tile tone-${item.tone ?? "default"}`} key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </article>
      ))}
    </section>
  );
}
