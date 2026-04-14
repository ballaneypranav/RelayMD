import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

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
            latest_checkpoint_path: null,
            last_checkpoint_at: "2026-02-24T11:58:45Z",
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
    expect(screen.getByText("Job states")).toBeInTheDocument();
    expect(screen.getByText("Worker states")).toBeInTheDocument();
    expect(screen.queryByText(/Orchestrator:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Refresh:/)).not.toBeInTheDocument();
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

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Workers/i }));
    });
    expect(screen.getByText("Fleet health")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByText("Clusters"));
    });
    expect(screen.getByRole("heading", { name: "Provisioning targets" })).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByText("Settings"));
    });
    expect(
      screen.getByText(/The proxy injects the RelayMD API token upstream/),
    ).toBeInTheDocument();
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
});
