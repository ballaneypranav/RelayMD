import { fireEvent, render, screen, waitFor } from "@testing-library/react";

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
    window.localStorage.clear();
  });

  it("loads dashboard data after token save", async () => {
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

    fireEvent.change(screen.getByPlaceholderText("Enter RELAYMD_API_TOKEN"), {
      target: { value: "secret-token" },
    });
    fireEvent.click(screen.getByText("Save token"));

    await waitFor(() => expect(screen.getByText("protein-folding")).toBeInTheDocument());
    expect(screen.getByText("Token saved locally for this browser.")).toBeInTheDocument();
  });

  it("shows offline state when dashboard data fails", async () => {
    mockFetch({
      "GET /config/frontend": new Response(
        JSON.stringify({ api_base_url: "", refresh_interval_seconds: 30 }),
      ),
      "GET /jobs": new Response("boom", { status: 503 }),
      "GET /workers": new Response(JSON.stringify([])),
      "GET /config/slurm-clusters": new Response(JSON.stringify({ clusters: [] })),
      "GET /healthz": new Response(JSON.stringify({ status: "ok", version: "0.1.4", warnings: [] })),
    });

    render(<App />);
    fireEvent.change(screen.getByPlaceholderText("Enter RELAYMD_API_TOKEN"), {
      target: { value: "secret-token" },
    });
    fireEvent.click(screen.getByText("Save token"));

    await waitFor(() => expect(screen.getByText("Orchestrator unreachable")).toBeInTheDocument());
  });
});
