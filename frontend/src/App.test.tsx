import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { App } from "./App";

function mockFetch(routes: Record<string, Response>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const key = `${init?.method ?? "GET"} ${url}`;
      const response = routes[key] ?? routes[`GET ${url}`];
      if (!response) {
        throw new Error(`Unexpected request: ${key}`);
      }
      return Promise.resolve(response.clone());
    }),
  );
}

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.history.replaceState(null, "", "/");
  });

  it("loads dashboard data through the proxy without a browser-held api token", async () => {
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(
        JSON.stringify([
          {
            id: "job-1",
            title: "protein-folding",
            status: "running",
            input_bundle_path: "/tmp/input",
            assigned_at: "2026-02-24T11:10:00Z",
            started_at: "2026-02-24T11:20:00Z",
            status_changed_at: "2026-02-24T11:20:00Z",
            latest_checkpoint_path: null,
            last_checkpoint_at: "2026-02-24T11:58:45Z",
            progress: 0.4,
            progress_codes: [],
            checkpoint_cycle_status: "success",
            checkpoint_cycle_failures: [],
            assigned_worker_id: "worker-1",
            created_at: "2026-02-24T11:00:00Z",
            updated_at: "2026-02-24T11:50:00Z",
          },
        ]),
      ),
      "GET /workers": new Response(
        JSON.stringify([
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
        ]),
      ),
      "GET /config/slurm-clusters": new Response(JSON.stringify({ clusters: [] })),
      "GET /healthz": new Response(
        JSON.stringify({
          status: "ok",
          version: "0.1.4",
          warnings: [],
          tailscale: { connected: true, hostname: "relaymd" },
        }),
      ),
    });

    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /protein-folding/i })).toBeInTheDocument(),
    );
    expect(screen.getByText("Execution queue")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "CONNECTED" })).toBeInTheDocument();
    expect(screen.getByText("RelayMD v0.1.4")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
    expect(screen.getByText("Job states")).toBeInTheDocument();
    expect(screen.getByText("Worker states")).toBeInTheDocument();
    expect(screen.getByText(/Last updated/i)).toBeInTheDocument();
  });

  it("shows offline state when dashboard data fails", async () => {
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response("boom", { status: 503 }),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(JSON.stringify({ clusters: [] })),
      "GET /healthz": new Response(
        JSON.stringify({ status: "ok", version: "0.1.4", warnings: [] }),
      ),
    });

    render(<App />);

    await waitFor(() => expect(screen.getByText(/Orchestrator unreachable/)).toBeInTheDocument());
  });

  it("navigates between major views and shows proxy auth guidance in settings", async () => {
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
    });

    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Workers/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByLabelText("RelayMD Operator Console")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Jobs" })).toHaveClass("active");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Workers/i }));
    });
    expect(window.location.pathname).toBe("/app/workers");
    expect(screen.getByText("Fleet health")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByText("Clusters"));
    });
    expect(window.location.pathname).toBe("/app/clusters");
    expect(screen.getByRole("heading", { name: "Provisioning targets" })).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByText("Settings"));
    });
    expect(window.location.pathname).toBe("/app/settings");
    expect(
      screen.getByText(/The proxy injects the RelayMD API token upstream/),
    ).toBeInTheDocument();
  });

  it("renders workers as a dense table with filters and expandable details", async () => {
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(
        JSON.stringify([
          {
            id: "job-1",
            title: "protein-folding",
            status: "running",
            input_bundle_path: "/tmp/input",
            assigned_at: "2026-02-24T11:10:00Z",
            started_at: "2026-02-24T11:20:00Z",
            status_changed_at: "2026-02-24T11:20:00Z",
            latest_checkpoint_path: null,
            latest_checkpoint_manifest_path: null,
            last_checkpoint_at: null,
            progress: 0.4,
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
        ]),
      ),
      "GET /workers": new Response(
        JSON.stringify([
          {
            id: "worker-1",
            platform: "salad",
            gpu_model: "NVIDIA A100",
            gpu_count: 1,
            vram_gb: 80,
            status: "active",
            provider_id: "provider-1",
            provider_state: "running",
            provider_state_raw: "RUNNING",
            provider_reason: null,
            provider_last_checked_at: "2026-02-24T11:59:00Z",
            last_heartbeat: "2026-02-24T11:59:30Z",
            registered_at: "2026-02-24T09:00:00Z",
          },
        ]),
      ),
      "GET /config/slurm-clusters": new Response(JSON.stringify({ clusters: [] })),
      "GET /healthz": new Response(JSON.stringify({ status: "ok", version: "0.1.4", warnings: [] })),
      "GET /jobs/job-1/history": new Response(
        JSON.stringify({ derived: true, worker_segments: [], worker_totals: [], events: [] }),
      ),
    });

    render(<App />);

    await waitFor(() => expect(screen.getByRole("button", { name: /Workers/i })).toBeInTheDocument());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Workers/i }));
    });

    expect(screen.getByRole("table", { name: "Workers table" })).toBeInTheDocument();
    expect(screen.getByText("worker-1")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByText("Filters"));
      fireEvent.click(screen.getByRole("checkbox", { name: "stale" }));
    });
    await waitFor(() =>
      expect(screen.getByText("Worker data will appear here after the first worker registration heartbeat.")).toBeInTheDocument(),
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("checkbox", { name: "stale" }));
    });
    await waitFor(() => expect(screen.getByText("worker-1")).toBeInTheDocument());

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Expand row" }));
    });
    expect(screen.getByText("Provider Raw State")).toBeInTheDocument();
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
  });

  it("renders jobs as a dense table with search, filter, sort, pagination, column visibility, selection, and expansion", async () => {
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(
        JSON.stringify([
          {
            id: "job-1",
            title: "alpha-job",
            status: "running",
            input_bundle_path: "/tmp/input",
            assigned_at: "2026-02-24T11:10:00Z",
            started_at: "2026-02-24T11:20:00Z",
            status_changed_at: "2026-02-24T11:20:00Z",
            latest_checkpoint_path: null,
            latest_checkpoint_manifest_path: null,
            last_checkpoint_at: null,
            progress: 0.4,
            progress_codes: [],
            checkpoint_cycle_status: null,
            checkpoint_cycle_failures: [],
            preferred_clusters: [],
            comment: null,
            queue_blocked_reason: null,
            assigned_worker_id: "worker-1",
            created_at: "2026-02-24T11:00:00Z",
            updated_at: "2026-02-24T11:50:00Z",
          },
          {
            id: "job-2",
            title: "beta-job",
            status: "queued",
            input_bundle_path: "/tmp/input",
            assigned_at: null,
            started_at: null,
            status_changed_at: "2026-02-24T11:20:00Z",
            latest_checkpoint_path: null,
            latest_checkpoint_manifest_path: null,
            last_checkpoint_at: null,
            progress: 0.0,
            progress_codes: [],
            checkpoint_cycle_status: null,
            checkpoint_cycle_failures: [],
            preferred_clusters: [],
            comment: null,
            queue_blocked_reason: null,
            assigned_worker_id: null,
            created_at: "2026-02-24T11:00:00Z",
            updated_at: "2026-02-24T11:50:00Z",
          },
        ]),
      ),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(JSON.stringify({ clusters: [] })),
      "GET /healthz": new Response(JSON.stringify({ status: "ok", version: "0.1.4", warnings: [] })),
      "GET /jobs/job-1/history": new Response(
        JSON.stringify({ derived: true, worker_segments: [], worker_totals: [], events: [] }),
      ),
    });

    render(<App />);

    await waitFor(() => expect(screen.getByRole("table", { name: "Jobs" })).toBeInTheDocument());
    expect(screen.getByText("alpha-job")).toBeInTheDocument();
    expect(screen.getByText("beta-job")).toBeInTheDocument();

    // Expansion
    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Expand row" })[0]);
    });
    expect(screen.getByText("Input Bundle")).toBeInTheDocument();

    // Selection
    await act(async () => {
      fireEvent.click(screen.getByRole("checkbox", { name: "Select row job-1" }));
    });
    expect(screen.getByRole("button", { name: "Bulk cancel selected jobs" })).toBeInTheDocument();

    // Column visibility
    const table = screen.getByRole("table", { name: "Jobs" });
    await act(async () => {
      fireEvent.click(screen.getByText("Columns"));
      fireEvent.click(screen.getByRole("checkbox", { name: "Status" }));
    });
    await waitFor(() => expect(within(table).queryByText("queued")).not.toBeInTheDocument());

    // Search
    const searchInput = screen.getByRole("searchbox", { name: "Search table" });
    await act(async () => {
      fireEvent.change(searchInput, { target: { value: "alpha" } });
    });
    expect(screen.getByText("alpha-job")).toBeInTheDocument();
    expect(screen.queryByText("beta-job")).not.toBeInTheDocument();

    // Clear search
    await act(async () => {
      fireEvent.change(searchInput, { target: { value: "" } });
    });

    // Filter
    await act(async () => {
      fireEvent.click(screen.getByText("Filters"));
      fireEvent.click(screen.getByRole("checkbox", { name: "running" }));
    });
    await waitFor(() => expect(within(table).queryByText("alpha-job")).not.toBeInTheDocument());
    expect(screen.getByText("beta-job")).toBeInTheDocument();
  });

  it("hydrates active view from URL and keeps it on reload-like mount", async () => {
    window.history.replaceState(null, "", "/app/workers");
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(JSON.stringify([])),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(JSON.stringify({ clusters: [] })),
      "GET /healthz": new Response(
        JSON.stringify({ status: "ok", version: "0.1.4", warnings: [] }),
      ),
    });

    render(<App />);

    await waitFor(() => expect(screen.getByText("Fleet health")).toBeInTheDocument());
    expect(window.location.pathname).toBe("/app/workers");
  });

  it("normalizes unknown routes to /app/jobs", async () => {
    window.history.replaceState(null, "", "/app/nope");
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(JSON.stringify([])),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(JSON.stringify({ clusters: [] })),
      "GET /healthz": new Response(
        JSON.stringify({ status: "ok", version: "0.1.4", warnings: [] }),
      ),
    });

    render(<App />);

    await waitFor(() => expect(window.location.pathname).toBe("/app/jobs"));
    expect(screen.getByText("Execution queue")).toBeInTheDocument();
  });

  it("opens connection details when the connected pill is clicked", async () => {
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(JSON.stringify([])),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(JSON.stringify({ clusters: [] })),
      "GET /healthz": new Response(
        JSON.stringify({
          status: "ok",
          version: "0.1.4",
          warnings: [],
          tailscale: { connected: true, hostname: "relaymd" },
        }),
      ),
    });

    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "CONNECTED" })).toBeInTheDocument(),
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "CONNECTED" }));
    });

    expect(
      screen.getByText(/The proxy injects the RelayMD API token upstream/),
    ).toBeInTheDocument();
  });

  it("keeps rendering with missing health version payload", async () => {
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(JSON.stringify([])),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(JSON.stringify({ clusters: [] })),
      "GET /healthz": new Response(JSON.stringify({ status: "ok", warnings: [] })),
    });

    render(<App />);

    await waitFor(() => expect(screen.getByText("RelayMD v-")).toBeInTheDocument());
  });

  it("tracks unsaved cluster toggle changes and saves them", async () => {
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(JSON.stringify([])),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(
        JSON.stringify({
          clusters: [
            {
              name: "gilbreth",
              partition: "gpu",
              strategy: "reactive",
              max_pending_jobs: 1,
              wall_time: "4:00:00",
              enabled: true,
            },
          ],
        }),
      ),
      "GET /healthz": new Response(JSON.stringify({ status: "ok", warnings: [] })),
      "PUT /config/slurm-clusters/enabled": new Response(null, { status: 204 }),
    });

    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Clusters/i })).toBeInTheDocument());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Clusters/i }));
    });

    const checkbox = await screen.findByRole("checkbox", { name: /Toggle gilbreth provisioning/i });
    fireEvent.click(checkbox);
    expect(screen.getByText("1 unsaved changes")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(screen.getByText("Cluster provisioning settings updated")).toBeInTheDocument());
  });

  it("keeps local cluster edits when save fails", async () => {
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(JSON.stringify([])),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(
        JSON.stringify({
          clusters: [
            {
              name: "gilbreth",
              partition: "gpu",
              strategy: "reactive",
              max_pending_jobs: 1,
              wall_time: "4:00:00",
              enabled: true,
            },
          ],
        }),
      ),
      "GET /healthz": new Response(JSON.stringify({ status: "ok", warnings: [] })),
      "PUT /config/slurm-clusters/enabled": new Response("save failed", { status: 500 }),
    });

    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Clusters/i })).toBeInTheDocument());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Clusters/i }));
    });

    const checkbox = await screen.findByRole("checkbox", { name: /Toggle gilbreth provisioning/i });
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(screen.getByText(/save failed/i)).toBeInTheDocument());
    expect(screen.getByText("1 unsaved changes")).toBeInTheDocument();
  });

  it("renders clusters as a dense table with filters and expandable details", async () => {
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(JSON.stringify([])),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(
        JSON.stringify({
          clusters: [
            {
              name: "gilbreth",
              partition: "gpu",
              strategy: "reactive",
              max_pending_jobs: 1,
              wall_time: "4:00:00",
              enabled: true,
            },
            {
              name: "negishi",
              partition: "A100",
              strategy: "reactive",
              max_pending_jobs: 2,
              wall_time: "8:00:00",
              enabled: false,
            },
          ],
        }),
      ),
      "GET /healthz": new Response(JSON.stringify({ status: "ok", warnings: [] })),
    });

    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Clusters/i })).toBeInTheDocument());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Clusters/i }));
    });

    expect(screen.getByRole("table", { name: "Clusters table" })).toBeInTheDocument();
    expect(screen.getByText("gilbreth")).toBeInTheDocument();
    expect(screen.getByText("negishi")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByText("Filters"));
      const group = screen.getByRole("group", { name: "Status" });
      fireEvent.click(within(group).getByRole("checkbox", { name: "Enabled" }));
    });
    await waitFor(() => expect(screen.queryByText("gilbreth")).not.toBeInTheDocument());
    expect(screen.getByText("negishi")).toBeInTheDocument();

    await act(async () => {
      const group = screen.getByRole("group", { name: "Status" });
      fireEvent.click(within(group).getByRole("checkbox", { name: "Enabled" }));
    });

    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Expand row" })[0]);
    });
    expect(screen.getAllByText("Max Pending Jobs")[0]).toBeInTheDocument();
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
  });

  it("shows history source as unavailable when history fetch fails", async () => {
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(
        JSON.stringify([
          {
            id: "job-1",
            title: "protein-folding",
            status: "running",
            input_bundle_path: "/tmp/input",
            assigned_at: "2026-02-24T11:10:00Z",
            started_at: "2026-02-24T11:20:00Z",
            status_changed_at: "2026-02-24T11:20:00Z",
            latest_checkpoint_path: null,
            last_checkpoint_at: "2026-02-24T11:58:45Z",
            progress: 0.4,
            progress_codes: [],
            checkpoint_cycle_status: "success",
            checkpoint_cycle_failures: [],
            assigned_worker_id: "worker-1",
            created_at: "2026-02-24T11:00:00Z",
            updated_at: "2026-02-24T11:50:00Z",
          },
        ]),
      ),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(JSON.stringify({ clusters: [] })),
      "GET /healthz": new Response(JSON.stringify({ status: "ok", version: "0.1.4", warnings: [] })),
      "GET /jobs/job-1/history": new Response("boom", { status: 500 }),
    });

    render(<App />);

    await waitFor(() => expect(screen.getByRole("button", { name: /protein-folding/i })).toBeInTheDocument());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /protein-folding/i }));
    });

    await waitFor(() => expect(screen.getByText("History Source")).toBeInTheDocument());
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("enables bulk cancel only for cancellable selected jobs", async () => {
    const jobs = [
      {
        id: "job-1",
        title: "queued-job",
        status: "queued",
        input_bundle_path: "/tmp/input",
        preferred_clusters: [],
        comment: null,
        queue_blocked_reason: null,
        assigned_at: null,
        started_at: null,
        status_changed_at: "2026-02-24T11:20:00Z",
        latest_checkpoint_manifest_path: null,
        latest_checkpoint_path: null,
        last_checkpoint_at: null,
        progress: 0,
        progress_codes: [],
        checkpoint_cycle_status: null,
        checkpoint_cycle_failures: [],
        assigned_worker_id: null,
        created_at: "2026-02-24T11:00:00Z",
        updated_at: "2026-02-24T11:50:00Z",
      },
      {
        id: "job-2",
        title: "failed-job",
        status: "failed",
        input_bundle_path: "/tmp/input2",
        preferred_clusters: [],
        comment: null,
        queue_blocked_reason: null,
        assigned_at: null,
        started_at: null,
        status_changed_at: "2026-02-24T11:20:00Z",
        latest_checkpoint_manifest_path: null,
        latest_checkpoint_path: null,
        last_checkpoint_at: null,
        progress: 0,
        progress_codes: [],
        checkpoint_cycle_status: null,
        checkpoint_cycle_failures: [],
        assigned_worker_id: null,
        created_at: "2026-02-24T11:00:00Z",
        updated_at: "2026-02-24T11:50:00Z",
      },
    ];
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(JSON.stringify(jobs)),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(JSON.stringify({ clusters: [] })),
      "GET /healthz": new Response(JSON.stringify({ status: "ok", version: "0.1.4", warnings: [] })),
      "GET /jobs/job-1/history": new Response(
        JSON.stringify({ derived: true, worker_segments: [], worker_totals: [], events: [] }),
      ),
      "DELETE /jobs/job-1?force=true": new Response(null, { status: 204 }),
    });

    render(<App />);

    await waitFor(() => expect(screen.getByRole("button", { name: /queued-job/i })).toBeInTheDocument());
    const bulkCancel = screen.getByRole("button", { name: "Bulk cancel selected jobs" });
    expect(bulkCancel).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: "Select row job-1" }));
    expect(bulkCancel).toBeEnabled();

    fireEvent.click(screen.getByRole("checkbox", { name: "Select row job-2" }));
    expect(bulkCancel).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: "Select row job-2" }));
    fireEvent.click(bulkCancel);

    await waitFor(() => expect(screen.getByText("Cancel queued-job?")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Confirm cancellation" }));
    await waitFor(() => expect(screen.getByText("Job cancelled")).toBeInTheDocument());
  });

  it("enables bulk requeue only for requeueable selected jobs", async () => {
    const jobs = [
      {
        id: "job-1",
        title: "failed-job",
        status: "failed",
        input_bundle_path: "/tmp/input",
        preferred_clusters: [],
        comment: null,
        queue_blocked_reason: null,
        assigned_at: null,
        started_at: null,
        status_changed_at: "2026-02-24T11:20:00Z",
        latest_checkpoint_manifest_path: null,
        latest_checkpoint_path: null,
        last_checkpoint_at: null,
        progress: 0,
        progress_codes: [],
        checkpoint_cycle_status: null,
        checkpoint_cycle_failures: [],
        assigned_worker_id: null,
        created_at: "2026-02-24T11:00:00Z",
        updated_at: "2026-02-24T11:50:00Z",
      },
      {
        id: "job-2",
        title: "running-job",
        status: "running",
        input_bundle_path: "/tmp/input2",
        preferred_clusters: [],
        comment: null,
        queue_blocked_reason: null,
        assigned_at: "2026-02-24T11:10:00Z",
        started_at: "2026-02-24T11:20:00Z",
        status_changed_at: "2026-02-24T11:20:00Z",
        latest_checkpoint_manifest_path: null,
        latest_checkpoint_path: null,
        last_checkpoint_at: null,
        progress: 0.1,
        progress_codes: [],
        checkpoint_cycle_status: null,
        checkpoint_cycle_failures: [],
        assigned_worker_id: null,
        created_at: "2026-02-24T11:00:00Z",
        updated_at: "2026-02-24T11:50:00Z",
      },
    ];
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response(JSON.stringify(jobs)),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(JSON.stringify({ clusters: [] })),
      "GET /healthz": new Response(JSON.stringify({ status: "ok", version: "0.1.4", warnings: [] })),
      "GET /jobs/job-1/history": new Response(
        JSON.stringify({ derived: true, worker_segments: [], worker_totals: [], events: [] }),
      ),
      "POST /jobs/job-1/requeue": new Response(JSON.stringify({ ...jobs[0], id: "job-3" })),
    });

    render(<App />);

    await waitFor(() => expect(screen.getByRole("button", { name: /failed-job/i })).toBeInTheDocument());
    const bulkRequeue = screen.getByRole("button", { name: "Bulk requeue selected jobs" });
    expect(bulkRequeue).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: "Select row job-1" }));
    expect(bulkRequeue).toBeEnabled();

    fireEvent.click(screen.getByRole("checkbox", { name: "Select row job-2" }));
    expect(bulkRequeue).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: "Select row job-2" }));
    fireEvent.click(bulkRequeue);
    await waitFor(() => expect(screen.getByText("Re-queued as job job-3")).toBeInTheDocument());
  });

  it("ignores stale job-history responses for previously selected jobs", async () => {
    let resolveJob1History: ((value: Response) => void) | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        const key = `${init?.method ?? "GET"} ${url}`;
        if (key === "GET /config/frontend") {
          return Promise.resolve(
            new Response(JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 })),
          );
        }
        if (key === "GET /jobs") {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                {
                  id: "job-1",
                  title: "first-job",
                  status: "running",
                  input_bundle_path: "/tmp/input",
                  assigned_at: "2026-02-24T11:10:00Z",
                  started_at: "2026-02-24T11:20:00Z",
                  status_changed_at: "2026-02-24T11:20:00Z",
                  latest_checkpoint_path: null,
                  last_checkpoint_at: "2026-02-24T11:58:45Z",
                  progress: 0.4,
                  progress_codes: [],
                  checkpoint_cycle_status: "success",
                  checkpoint_cycle_failures: [],
                  assigned_worker_id: "worker-1",
                  created_at: "2026-02-24T11:00:00Z",
                  updated_at: "2026-02-24T11:50:00Z",
                },
                {
                  id: "job-2",
                  title: "second-job",
                  status: "running",
                  input_bundle_path: "/tmp/input2",
                  assigned_at: "2026-02-24T11:10:00Z",
                  started_at: "2026-02-24T11:20:00Z",
                  status_changed_at: "2026-02-24T11:20:00Z",
                  latest_checkpoint_path: null,
                  last_checkpoint_at: "2026-02-24T11:58:45Z",
                  progress: 0.6,
                  progress_codes: [],
                  checkpoint_cycle_status: "success",
                  checkpoint_cycle_failures: [],
                  assigned_worker_id: "worker-2",
                  created_at: "2026-02-24T11:00:00Z",
                  updated_at: "2026-02-24T11:50:00Z",
                },
              ]),
            ),
          );
        }
        if (key === "GET /workers") {
          return Promise.resolve(new Response(JSON.stringify([])));
        }
        if (key === "GET /config/slurm-clusters") {
          return Promise.resolve(new Response(JSON.stringify({ clusters: [] })));
        }
        if (key === "GET /healthz") {
          return Promise.resolve(
            new Response(JSON.stringify({ status: "ok", version: "0.1.4", warnings: [] })),
          );
        }
        if (key === "GET /jobs/job-1/history") {
          return new Promise<Response>((resolve) => {
            resolveJob1History = resolve;
          });
        }
        if (key === "GET /jobs/job-2/history") {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                derived: false,
                worker_segments: [],
                worker_totals: [],
                events: [
                  {
                    occurred_at: "2026-02-24T11:21:00Z",
                    event_seq: 1,
                    event_type: "second-history",
                    worker_id: "worker-2",
                    status_from: null,
                    status_to: "running",
                    payload: {},
                    derived: false,
                  },
                ],
              }),
            ),
          );
        }
        throw new Error(`Unexpected request: ${key}`);
      }),
    );

    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: /second-job/i })).toBeInTheDocument());

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /second-job/i }));
    });

    await waitFor(() => expect(screen.getByText(/second-history/)).toBeInTheDocument());

    await act(async () => {
      resolveJob1History?.(
        new Response(
          JSON.stringify({
            derived: false,
            worker_segments: [],
            worker_totals: [],
            events: [
              {
                occurred_at: "2026-02-24T11:22:00Z",
                event_seq: 1,
                event_type: "first-history-stale",
                worker_id: "worker-1",
                status_from: null,
                status_to: "running",
                payload: {},
                derived: false,
              },
            ],
          }),
        ),
      );
    });

    expect(screen.getByText(/second-history/)).toBeInTheDocument();
    expect(screen.queryByText(/first-history-stale/)).not.toBeInTheDocument();
  });
});
