import type { ReactNode } from "react";

interface StatusPillProps {
  children: ReactNode;
  className?: string;
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

export function StatusPill({ children, className = "", tone = "queued" }: StatusPillProps) {
  return <span className={`status-pill tone-${tone} ${className}`.trim()}>{children}</span>;
}
