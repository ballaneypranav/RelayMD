import type {
  ClusterConfig,
  DashboardPayload,
  FrontendConfig,
  HealthStatus,
  JobRead,
  WorkerRead,
} from "./types";

function authHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
    "X-API-Token": token,
  };
}

async function readJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function fetchFrontendConfig(): Promise<FrontendConfig> {
  return readJson<FrontendConfig>("/config/frontend");
}

export async function fetchDashboardData(
  apiBaseUrl: string,
  token: string,
): Promise<DashboardPayload> {
  const base = apiBaseUrl || "";
  const headers = authHeaders(token);
  const [jobs, workers, clustersPayload, health] = await Promise.all([
    readJson<JobRead[]>(`${base}/jobs`, { headers }),
    readJson<WorkerRead[]>(`${base}/workers`, { headers }),
    readJson<{ clusters: ClusterConfig[] }>(`${base}/config/slurm-clusters`, { headers }),
    readJson<HealthStatus>(`${base}/healthz`),
  ]);

  return {
    jobs,
    workers,
    clusters: clustersPayload.clusters,
    health,
  };
}

export async function cancelJob(apiBaseUrl: string, token: string, jobId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/jobs/${jobId}?force=true`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (response.status === 204) {
    return;
  }
  throw new Error((await response.text()) || `Cancel failed (${response.status})`);
}

export async function requeueJob(
  apiBaseUrl: string,
  token: string,
  jobId: string,
): Promise<string> {
  const response = await fetch(`${apiBaseUrl}/jobs/${jobId}/requeue`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!response.ok) {
    throw new Error((await response.text()) || `Re-queue failed (${response.status})`);
  }
  const payload = (await response.json()) as JobRead;
  return payload.id;
}
