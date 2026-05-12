import type { JobRead, JobWorkerSegment, WorkerRead } from "./types";

const STALE_WORKER_SECONDS = 120;

export function parseDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const normalizedValue = /[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`;
  const parsed = new Date(normalizedValue);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatDuration(deltaSeconds: number): string {
  const totalSeconds = Math.max(Math.trunc(deltaSeconds), 0);
  const units: Array<[string, number]> = [
    ["mo", 30 * 24 * 60 * 60],
    ["d", 24 * 60 * 60],
    ["h", 60 * 60],
    ["m", 60],
  ];

  const parts: string[] = [];
  let remainder = totalSeconds;
  for (const [suffix, unitSeconds] of units) {
    const value = Math.floor(remainder / unitSeconds);
    remainder %= unitSeconds;
    if (value > 0) {
      parts.push(`${value}${suffix}`);
    }
  }

  if (parts.length >= 2) {
    return parts.slice(0, 2).join(" ");
  }
  if (parts.length === 1) {
    return remainder > 0 ? `${parts[0]} ${remainder}s` : parts[0];
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m ${seconds}s`;
}

export function truncateUuid(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return value.length <= 12 ? value : `${value.slice(0, 8)}...`;
}

export interface JobRow {
  id: string;
  job_id: string;
  title: string;
  status: string;
  age: string;
  time_in_status: string;
  assigned_worker_id: string;
  time_since_checkpoint: string;
  progress: string;
  checkpoint_health: string;
}

export interface WorkerRow {
  id: string;
  platform: string;
  gpu: string;
  provider_id: string;
  provider_state: string;
  uptime: string;
  last_heartbeat: string;
  current_job: string;
  status: string;
}

export function totalRuntimeSeconds(job: JobRead, now: Date, segments?: JobWorkerSegment[]): number {
  if (segments && segments.length > 0) {
    return segments.reduce((total, segment) => total + Math.max(0, segment.duration_seconds), 0);
  }
  const startedAt = parseDate(job.started_at);
  const assignedAt = parseDate(job.assigned_at);
  const terminalAt = parseDate(job.status_changed_at);
  const active = job.status === "assigned" || job.status === "running";
  const segmentStart = startedAt ?? assignedAt;
  if (!segmentStart) {
    return 0;
  }
  if (active) {
    return Math.max(0, (now.getTime() - segmentStart.getTime()) / 1000);
  }
  if (!terminalAt) {
    return 0;
  }
  return Math.max(0, (terminalAt.getTime() - segmentStart.getTime()) / 1000);
}

export function etaSeconds(job: JobRead, now: Date, segments?: JobWorkerSegment[]): number | null {
  if (job.status !== "assigned" && job.status !== "running") {
    return null;
  }
  const rawProgress = job.progress ?? 0;
  const progress = Math.max(0, Math.min(1, rawProgress));
  if (progress <= 0 || progress >= 1) {
    return null;
  }
  const runtime = totalRuntimeSeconds(job, now, segments);
  const estimatedTotal = runtime / progress;
  return Math.max(0, estimatedTotal - runtime);
}

export function buildJobRows(rawJobs: JobRead[], now: Date): JobRow[] {
  return rawJobs.map((job) => {
    const checkpointAt = parseDate(job.last_checkpoint_at);
    const createdAt = parseDate(job.created_at);
    const statusChangedAt = parseDate(job.status_changed_at);

    return {
      id: job.id,
      job_id: truncateUuid(job.id),
      title: job.title || "-",
      status: job.status,
      age: createdAt ? formatDuration((now.getTime() - createdAt.getTime()) / 1000) : "-",
      time_in_status: statusChangedAt
        ? formatDuration((now.getTime() - statusChangedAt.getTime()) / 1000)
        : "-",
      assigned_worker_id: truncateUuid(job.assigned_worker_id),
      time_since_checkpoint: checkpointAt
        ? formatDuration((now.getTime() - checkpointAt.getTime()) / 1000)
        : "-",
      progress: `${Math.round(((job.progress ?? 0) * 100) * 10) / 10}%`,
      checkpoint_health: job.checkpoint_cycle_failures.length > 0 ? "warn" : "ok",
    };
  });
}

export function buildWorkerRows(rawWorkers: WorkerRead[], now: Date, rawJobs: JobRead[]): WorkerRow[] {
  const workerJob = new Map<string, string>();
  for (const job of rawJobs) {
    if (!job.assigned_worker_id) {
      continue;
    }
    if (job.status !== "running" && job.status !== "assigned") {
      continue;
    }
    workerJob.set(
      job.assigned_worker_id,
      `${job.title.slice(0, 24)} (${truncateUuid(job.id)})`,
    );
  }

  return rawWorkers.map((worker) => {
    const heartbeatAt = parseDate(worker.last_heartbeat);
    const registeredAt = parseDate(worker.registered_at);
    let status = worker.status === "queued" ? "provisioning" : "active";
    let heartbeatText = "-";

    if (heartbeatAt) {
      heartbeatText = heartbeatAt.toISOString().slice(11, 19) + " UTC";
      if ((now.getTime() - heartbeatAt.getTime()) / 1000 > STALE_WORKER_SECONDS) {
        status = "stale";
      }
    } else {
      status = "stale";
    }

    if (worker.status === "queued") {
      status = "provisioning";
    }

    const gpu =
      worker.vram_gb !== null && worker.vram_gb !== undefined
        ? `${worker.gpu_count}x ${worker.gpu_model} (${worker.vram_gb} GB)`
        : worker.gpu_model;

    return {
      id: worker.id,
      platform: worker.platform,
      gpu,
      provider_id: worker.provider_id || "-",
      provider_state: worker.provider_state || "-",
      uptime: registeredAt ? formatDuration((now.getTime() - registeredAt.getTime()) / 1000) : "-",
      last_heartbeat: heartbeatText,
      current_job: workerJob.get(worker.id) || "-",
      status,
    };
  });
}

export function toDelimited<T extends object>(rows: T[]): string {
  return toSeparatedValues(rows, "\t");
}

export function toCsv<T extends object>(rows: T[]): string {
  return toSeparatedValues(rows, ",");
}

function toSeparatedValues<T extends object>(rows: T[], separator: "\t" | ","): string {
  if (rows.length === 0) {
    return "";
  }
  const headers = Object.keys(rows[0]) as Array<keyof T>;
  const lines = [headers.map((header) => String(header)).join(separator)];
  for (const row of rows) {
    lines.push(
      headers
        .map((header) => formatSeparatedValue(String(row[header] ?? ""), separator))
        .join(separator),
    );
  }
  return lines.join("\n") + "\n";
}

function formatSeparatedValue(value: string, separator: "\t" | ","): string {
  if (separator === "\t") {
    return value;
  }
  if (/[",\n]/.test(value)) {
    return `"${value.replaceAll('"', '""')}"`;
  }
  return value;
}
