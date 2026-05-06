import {
  buildJobRows,
  buildWorkerRows,
  formatDuration,
  parseDate,
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
        latest_checkpoint_path: null,
        last_checkpoint_at: "2026-02-24T11:58:45Z",
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
    expect(buildWorkerRows(workers, now, jobs)[0].current_job).toContain("protein-folding");
  });

  it("renders TSV output", () => {
    expect(toDelimited([{ job_id: "abc", status: "assigned" }])).toBe(
      "job_id\tstatus\nabc\tassigned\n",
    );
  });

  it("renders CSV output", () => {
    expect(toCsv([{ job_id: "abc", title: "a,b" }])).toBe('job_id,title\nabc,"a,b"\n');
  });
});
