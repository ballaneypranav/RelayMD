import {
  buildJobRows,
  etaSeconds,
  buildWorkerRows,
  formatDuration,
  parseDate,
  totalRuntimeSeconds,
  toCsv,
  toDelimited,
  truncateUuid,
} from "./format";

describe("format helpers", () => {
  it("formats duration using larger units", () => {
    expect(formatDuration(3)).toBe("0m 3s");
    expect(formatDuration(23 * 60 + 3)).toBe("23m 3s");
    expect(formatDuration(66 * 60 + 49)).toBe("1h 6m");
  });

  it("truncates uuids", () => {
    expect(truncateUuid("0a05f971-0f5b-46cb-bd86-d13133f998aa")).toBe("0a05f971...");
  });

  it("parses timezone-less API timestamps as UTC", () => {
    expect(parseDate("2026-05-05T13:23:03")?.toISOString()).toBe("2026-05-05T13:23:03.000Z");
  });

  it("builds job and worker rows", () => {
    const now = new Date("2026-02-24T12:00:00Z");
    const jobs = [
      {
        id: "job-1",
        title: "protein-folding",
        status: "running" as const,
        input_bundle_path: "/tmp/input",
        assigned_at: "2026-02-24T11:10:00Z",
        started_at: "2026-02-24T11:20:00Z",
        status_changed_at: "2026-02-24T11:20:00Z",
        latest_checkpoint_path: null,
        latest_checkpoint_manifest_path: null,
        last_checkpoint_at: "2026-02-24T11:58:45Z",
        progress: 0.45,
        progress_codes: [],
        checkpoint_cycle_status: "success",
        checkpoint_cycle_failures: [],
        preferred_clusters: [],
        comment: null,
        queue_blocked_reason: null,
        assigned_worker_id: "worker-1",
        created_at: "2026-02-24T11:00:00Z",
        updated_at: "2026-02-24T11:50:00Z",
      },
    ];
    const workers = [
      {
        id: "worker-1",
        platform: "salad",
        gpu_model: "NVIDIA A100",
        gpu_count: 1,
        vram_gb: 80,
        status: "active",
        provider_id: null,
        provider_state: null,
        provider_state_raw: null,
        provider_reason: null,
        provider_last_checked_at: null,
        last_heartbeat: "2026-02-24T11:59:30Z",
        registered_at: "2026-02-24T09:00:00Z",
      },
    ];

    expect(buildJobRows(jobs, now)[0].time_since_checkpoint).toBe("1m 15s");
    expect(buildJobRows(jobs, now)[0].time_in_status).toBe("40m");
    expect(buildWorkerRows(workers, now, jobs)[0].current_job).toContain("protein-folding");
  });

  it("classifies worker statuses for active, provisioning, and stale", () => {
    const now = new Date("2026-02-24T12:00:00Z");
    const rows = buildWorkerRows(
      [
        {
          id: "worker-active",
          platform: "salad",
          gpu_model: "NVIDIA A100",
          gpu_count: 1,
          vram_gb: 80,
          status: "active",
          provider_id: null,
          provider_state: null,
          provider_state_raw: null,
          provider_reason: null,
          provider_last_checked_at: null,
          last_heartbeat: "2026-02-24T11:59:30Z",
          registered_at: "2026-02-24T09:00:00Z",
        },
        {
          id: "worker-queued",
          platform: "hpc",
          gpu_model: "NVIDIA A40",
          gpu_count: 1,
          vram_gb: 48,
          status: "queued",
          provider_id: null,
          provider_state: "PENDING",
          provider_state_raw: "PD",
          provider_reason: null,
          provider_last_checked_at: null,
          last_heartbeat: "2026-02-24T11:55:00Z",
          registered_at: "2026-02-24T11:40:00Z",
        },
        {
          id: "worker-stale",
          platform: "salad",
          gpu_model: "NVIDIA A100",
          gpu_count: 1,
          vram_gb: 80,
          status: "active",
          provider_id: null,
          provider_state: null,
          provider_state_raw: null,
          provider_reason: null,
          provider_last_checked_at: null,
          last_heartbeat: "2026-02-24T11:55:30Z",
          registered_at: "2026-02-24T09:00:00Z",
        },
      ],
      now,
      [],
    );

    expect(rows.find((row) => row.id === "worker-active")?.status).toBe("active");
    expect(rows.find((row) => row.id === "worker-queued")?.status).toBe("provisioning");
    expect(rows.find((row) => row.id === "worker-stale")?.status).toBe("stale");
    expect(rows.find((row) => row.id === "worker-active")?.last_heartbeat).toBe("11:59:30 UTC");
  });

  it("uses status_changed_at rather than updated_at for time in status", () => {
    const now = new Date("2026-02-24T12:00:00Z");
    const jobs = [
      {
        id: "job-1",
        title: "protein-folding",
        status: "running" as const,
        input_bundle_path: "/tmp/input",
        assigned_at: "2026-02-24T11:10:00Z",
        started_at: "2026-02-24T11:20:00Z",
        status_changed_at: "2026-02-24T11:20:00Z",
        latest_checkpoint_path: null,
        latest_checkpoint_manifest_path: null,
        last_checkpoint_at: "2026-02-24T11:58:45Z",
        progress: 0.45,
        progress_codes: [],
        checkpoint_cycle_status: "success",
        checkpoint_cycle_failures: [],
        preferred_clusters: [],
        comment: null,
        queue_blocked_reason: null,
        assigned_worker_id: "worker-1",
        created_at: "2026-02-24T11:00:00Z",
        updated_at: "2026-02-24T11:58:45Z",
      },
    ];

    const row = buildJobRows(jobs, now)[0];

    expect(row.time_in_status).toBe("40m");
    expect(row.time_since_checkpoint).toBe("1m 15s");
  });

  it("renders TSV output", () => {
    expect(toDelimited([{ job_id: "abc", status: "assigned" }])).toBe(
      "job_id\tstatus\nabc\tassigned\n",
    );
  });

  it("renders CSV output", () => {
    expect(toCsv([{ job_id: "abc", title: "a,b" }])).toBe('job_id,title\nabc,"a,b"\n');
  });

  it("computes total runtime for active and terminal jobs", () => {
    const now = new Date("2026-02-24T12:00:00Z");
    const runningJob = {
      id: "job-1",
      title: "protein-folding",
      status: "running" as const,
      input_bundle_path: "/tmp/input",
      assigned_at: "2026-02-24T11:10:00Z",
      started_at: "2026-02-24T11:20:00Z",
      status_changed_at: "2026-02-24T11:20:00Z",
      latest_checkpoint_path: null,
      latest_checkpoint_manifest_path: null,
      last_checkpoint_at: null,
      progress: 0.5,
      progress_codes: [],
      checkpoint_cycle_status: null,
      checkpoint_cycle_failures: [],
      preferred_clusters: [],
      comment: null,
      queue_blocked_reason: null,
      assigned_worker_id: "worker-1",
      created_at: "2026-02-24T11:00:00Z",
      updated_at: "2026-02-24T11:50:00Z",
    };
    const completedJob = {
      ...runningJob,
      status: "completed" as const,
      status_changed_at: "2026-02-24T11:45:00Z",
    };

    expect(totalRuntimeSeconds(runningJob, now)).toBe(40 * 60);
    expect(totalRuntimeSeconds(completedJob, now)).toBe(25 * 60);
  });

  it("computes eta and hides it for invalid cases", () => {
    const now = new Date("2026-02-24T12:00:00Z");
    const baseJob = {
      id: "job-1",
      title: "protein-folding",
      status: "running" as const,
      input_bundle_path: "/tmp/input",
      assigned_at: "2026-02-24T11:10:00Z",
      started_at: "2026-02-24T11:20:00Z",
      status_changed_at: "2026-02-24T11:20:00Z",
      latest_checkpoint_path: null,
      latest_checkpoint_manifest_path: null,
      last_checkpoint_at: null,
      progress: 0.5,
      progress_codes: [],
      checkpoint_cycle_status: null,
      checkpoint_cycle_failures: [],
      preferred_clusters: [],
      comment: null,
      queue_blocked_reason: null,
      assigned_worker_id: "worker-1",
      created_at: "2026-02-24T11:00:00Z",
      updated_at: "2026-02-24T11:50:00Z",
    };

    expect(etaSeconds(baseJob, now)).toBe(40 * 60);
    expect(etaSeconds({ ...baseJob, progress: 0 }, now)).toBeNull();
    expect(etaSeconds({ ...baseJob, progress: 1 }, now)).toBeNull();
    expect(etaSeconds({ ...baseJob, status: "completed" as const }, now)).toBeNull();
    expect(etaSeconds({ ...baseJob, progress: 1.2 }, now)).toBeNull();
    expect(etaSeconds({ ...baseJob, progress: -0.2 }, now)).toBeNull();
  });
});
