import type { JobRead, WorkerRead } from "./types";

const STALE_WORKER_SECONDS = 120;

export function parseDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
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
}

export interface WorkerRow {
  platform: string;
  gpu: string;
  provider_id: string;
  provider_state: string;
  uptime: string;
  last_heartbeat: string;
  current_job: string;
  status: string;
}

export function buildJobRows(rawJobs: JobRead[], now: Date): JobRow[] {
  return rawJobs.map((job) => {
    const checkpointAt = parseDate(job.last_checkpoint_at);
    const createdAt = parseDate(job.created_at);
    const updatedAt = parseDate(job.updated_at);

    return {
      id: job.id,
      job_id: truncateUuid(job.id),
      title: job.title || "-",
      status: job.status,
      age: createdAt ? formatDuration((now.getTime() - createdAt.getTime()) / 1000) : "-",
      time_in_status: updatedAt
        ? formatDuration((now.getTime() - updatedAt.getTime()) / 1000)
        : "-",
      assigned_worker_id: truncateUuid(job.assigned_worker_id),
      time_since_checkpoint: checkpointAt
        ? formatDuration((now.getTime() - checkpointAt.getTime()) / 1000)
        : "-",
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
