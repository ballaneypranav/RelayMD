interface StatusPillProps {
  children: string;
  tone?:
    | "queued"
    | "assigned"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
    | "active"
    | "stale"
    | "provisioning";
}

export function StatusPill({ children, tone = "queued" }: StatusPillProps) {
  return <span className={`status-pill tone-${tone}`}>{children}</span>;
}
