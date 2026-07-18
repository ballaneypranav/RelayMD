import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchDashboardData } from "./api";

const dashboardResponses: Record<string, unknown> = {
  "/jobs": [],
  "/workers": [],
  "/config/slurm-clusters": { clusters: [] },
  "/healthz": { status: "ok", warnings: [] },
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, statusText: "test" });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchDashboardData", () => {
  it("uses an empty worker-image catalog when the endpoint is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url === "/config/worker-images") {
        return Promise.resolve(response({ detail: "not found" }, 404));
      }
      return Promise.resolve(response(dashboardResponses[url]));
    }));

    await expect(fetchDashboardData("")).resolves.toMatchObject({
      workerImageCatalog: { default_worker_image: "", worker_images: [] },
    });
  });

  it("propagates worker-image catalog errors other than 404", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url === "/config/worker-images") {
        return Promise.resolve(response({ detail: "unavailable" }, 503));
      }
      return Promise.resolve(response(dashboardResponses[url]));
    }));

    await expect(fetchDashboardData("")).rejects.toThrow("unavailable");
  });
});
