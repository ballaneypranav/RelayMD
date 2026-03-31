import { useEffect, useMemo, useState } from "react";

import { cancelJob, fetchDashboardData, fetchFrontendConfig, requeueJob } from "./api";
import { buildJobRows, buildWorkerRows, formatDuration, parseDate, toDelimited } from "./format";
import { clearApiToken, loadApiToken, saveApiToken } from "./storage";
import type { DashboardPayload, FrontendConfig, JobRead } from "./types";

type TabName = "jobs" | "workers" | "clusters";

const JOB_STATUS_COLORS: Record<string, string> = {
  completed: "status-completed",
  running: "status-running",
  failed: "status-failed",
  queued: "status-queued",
  assigned: "status-assigned",
  cancelled: "status-cancelled",
};

function copyText(text: string): void {
  if (!text) {
    return;
  }
  void navigator.clipboard?.writeText(text);
}

function downloadText(filename: string, text: string, mime: string): void {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function useDashboardData(config: FrontendConfig | null, token: string) {
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [offlineSince, setOfflineSince] = useState<number | null>(null);

  useEffect(() => {
    if (!config || !token.trim()) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    const load = async () => {
      try {
        const payload = await fetchDashboardData(config.api_base_url, token);
        if (cancelled) {
          return;
        }
        setData(payload);
        setError("");
        setOfflineSince(null);
      } catch (loadError) {
        if (cancelled) {
          return;
        }
        const message = loadError instanceof Error ? loadError.message : String(loadError);
        setError(message);
        setOfflineSince((previous) => previous ?? Date.now());
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();
    const intervalId = window.setInterval(load, config.refresh_interval_seconds * 1000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [config, token]);

  return { data, error, loading, offlineSince, setData, setError };
}

export function App() {
  const [config, setConfig] = useState<FrontendConfig | null>(null);
  const [configError, setConfigError] = useState("");
  const [tokenInput, setTokenInput] = useState(loadApiToken);
  const [token, setToken] = useState(loadApiToken);
  const [activeTab, setActiveTab] = useState<TabName>("jobs");
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string>("");
  const [pendingCancelJob, setPendingCancelJob] = useState<JobRead | null>(null);
  const [actionMessage, setActionMessage] = useState<string>("");
  const [actionError, setActionError] = useState<string>("");

  const { data, error, loading, offlineSince, setData, setError } = useDashboardData(config, token);

  useEffect(() => {
    void fetchFrontendConfig()
      .then(setConfig)
      .catch((loadError) => {
        setConfigError(loadError instanceof Error ? loadError.message : String(loadError));
      });
  }, []);

  const now = useMemo(() => new Date(), [data, error]);
  const jobs = data?.jobs ?? [];
  const workers = data?.workers ?? [];
  const clusters = data?.clusters ?? [];
  const health = data?.health;

  const jobRows = useMemo(() => buildJobRows(jobs, now), [jobs, now]);
  const workerRows = useMemo(() => buildWorkerRows(workers, now, jobs), [workers, now, jobs]);
  const availableStatuses = useMemo(
    () => Array.from(new Set(jobRows.map((job) => job.status))).sort(),
    [jobRows],
  );

  useEffect(() => {
    if (availableStatuses.length > 0 && selectedStatuses.length === 0) {
      setSelectedStatuses(availableStatuses);
    }
  }, [availableStatuses, selectedStatuses.length]);

  useEffect(() => {
    if (!selectedJobId && jobs.length > 0) {
      setSelectedJobId(jobs[0].id);
    }
  }, [jobs, selectedJobId]);

  const filteredJobRows =
    selectedStatuses.length > 0
      ? jobRows.filter((job) => selectedStatuses.includes(job.status))
      : jobRows;
  const selectedJob = jobs.find((job) => job.id === selectedJobId) ?? null;

  const statusCounts = jobs.reduce<Record<string, number>>((counts, job) => {
    counts[job.status] = (counts[job.status] ?? 0) + 1;
    return counts;
  }, {});

  const activeWorkers = workers.filter((worker) => worker.status !== "queued").length;
  const provisioningWorkers = workers.filter((worker) => worker.status === "queued").length;

  const saveToken = () => {
    const trimmed = tokenInput.trim();
    saveApiToken(trimmed);
    setToken(trimmed);
    setActionMessage(trimmed ? "Token saved locally for this browser." : "");
    setActionError("");
  };

  const resetToken = () => {
    clearApiToken();
    setTokenInput("");
    setToken("");
    setData(null);
  };

  const handleCancel = async (job: JobRead) => {
    if (!config) {
      return;
    }
    try {
      await cancelJob(config.api_base_url, token, job.id);
      setActionMessage("Job cancelled");
      setActionError("");
      setPendingCancelJob(null);
      setError("");
      const payload = await fetchDashboardData(config.api_base_url, token);
      setData(payload);
    } catch (actionFailure) {
      setActionError(actionFailure instanceof Error ? actionFailure.message : String(actionFailure));
      setActionMessage("");
    }
  };

  const handleRequeue = async (job: JobRead) => {
    if (!config) {
      return;
    }
    try {
      const newJobId = await requeueJob(config.api_base_url, token, job.id);
      setActionMessage(`Re-queued as job ${newJobId}`);
      setActionError("");
      const payload = await fetchDashboardData(config.api_base_url, token);
      setData(payload);
    } catch (actionFailure) {
      setActionError(actionFailure instanceof Error ? actionFailure.message : String(actionFailure));
      setActionMessage("");
    }
  };

  if (configError) {
    return <div className="error-panel">Frontend config failed to load: {configError}</div>;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>RelayMD Operator Dashboard</h1>
        <p className="muted">
          Orchestrator: {config?.api_base_url || window.location.origin} | Refresh:{" "}
          {config?.refresh_interval_seconds ?? "-"}s
        </p>
        <section className="card">
          <h2>API Token</h2>
          <p className="muted">Stored in localStorage for this browser only.</p>
          <input
            type="password"
            value={tokenInput}
            onChange={(event) => setTokenInput(event.target.value)}
            placeholder="Enter RELAYMD_API_TOKEN"
          />
          <div className="button-row">
            <button onClick={saveToken}>Save token</button>
            <button className="secondary" onClick={resetToken}>
              Clear token
            </button>
          </div>
        </section>

        <section className="card">
          <h2>Manual Controls</h2>
          <p className="muted">
            No drain worker button is provided. Cancel assigned jobs and workers will stop on
            their next poll cycle.
          </p>
          <h3>Cancel Job</h3>
          <div className="list-group">
            {jobs
              .filter((job) => job.status === "queued" || job.status === "running")
              .map((job) => (
                <button
                  className="list-item"
                  key={`cancel-${job.id}`}
                  onClick={() => setPendingCancelJob(job)}
                >
                  {job.title} [{job.status}]
                </button>
              ))}
          </div>
          <h3>Re-queue Job</h3>
          <div className="list-group">
            {jobs
              .filter((job) => job.status === "failed" || job.status === "cancelled")
              .map((job) => (
                <button className="list-item" key={`requeue-${job.id}`} onClick={() => void handleRequeue(job)}>
                  {job.title} [{job.status}]
                </button>
              ))}
          </div>
        </section>

        {pendingCancelJob ? (
          <section className="card warning-panel">
            <h2>Confirm cancellation</h2>
            <p>Cancel job "{pendingCancelJob.title}"? This cannot be undone.</p>
            <div className="button-row">
              <button onClick={() => void handleCancel(pendingCancelJob)}>Confirm</button>
              <button className="secondary" onClick={() => setPendingCancelJob(null)}>
                Abort
              </button>
            </div>
          </section>
        ) : null}
      </aside>

      <main className="main-panel">
        {health?.warnings?.map((warning) => (
          <div className="banner warning" key={warning}>
            {warning}
          </div>
        ))}
        {health?.tailscale ? (
          health.tailscale.connected ? (
            <div className="banner success">
              Tailscale connected:{" "}
              {health.tailscale.hostname || health.tailscale.dns_name || health.tailscale.ip}
            </div>
          ) : (
            <div className="banner error">
              Tailscale not connected: {health.tailscale.error || "unknown error"}
            </div>
          )
        ) : null}
        {actionMessage ? <div className="banner success">{actionMessage}</div> : null}
        {actionError ? <div className="banner error">{actionError}</div> : null}

        {!token ? (
          <div className="card">
            <h2>API token required</h2>
            <p>Enter and save a RelayMD API token to load jobs, workers, and cluster config.</p>
          </div>
        ) : null}

        {error && offlineSince ? (
          <div className="card error-panel">
            <h2>Orchestrator unreachable</h2>
            <p>Offline for {formatDuration((Date.now() - offlineSince) / 1000)}</p>
            <pre>{error}</pre>
          </div>
        ) : null}

        <section className="metrics">
          <div className="metric-card">
            <span>Queued</span>
            <strong>{statusCounts.queued ?? 0}</strong>
          </div>
          <div className="metric-card">
            <span>Running</span>
            <strong>{statusCounts.running ?? 0}</strong>
          </div>
          <div className="metric-card">
            <span>Completed</span>
            <strong>{statusCounts.completed ?? 0}</strong>
          </div>
          <div className="metric-card">
            <span>Failed</span>
            <strong>{statusCounts.failed ?? 0}</strong>
          </div>
          <div className="metric-card">
            <span>Cancelled</span>
            <strong>{statusCounts.cancelled ?? 0}</strong>
          </div>
          <div className="metric-card">
            <span>Active Workers</span>
            <strong>{activeWorkers}</strong>
          </div>
          <div className="metric-card">
            <span>Provisioning</span>
            <strong>{provisioningWorkers}</strong>
          </div>
        </section>

        <nav className="tab-row">
          <button className={activeTab === "jobs" ? "tab active" : "tab"} onClick={() => setActiveTab("jobs")}>
            Jobs
          </button>
          <button
            className={activeTab === "workers" ? "tab active" : "tab"}
            onClick={() => setActiveTab("workers")}
          >
            Workers
          </button>
          <button
            className={activeTab === "clusters" ? "tab active" : "tab"}
            onClick={() => setActiveTab("clusters")}
          >
            Cluster Configs
          </button>
        </nav>

        {activeTab === "jobs" ? (
          <section className="card">
            <div className="section-header">
              <h2>Jobs</h2>
              <div className="button-row">
                <button onClick={() => copyText(toDelimited(filteredJobRows))}>Copy TSV</button>
                <button
                  className="secondary"
                  onClick={() =>
                    downloadText(
                      "relaymd-jobs.csv",
                      [Object.keys(filteredJobRows[0] ?? {}).join(","), ...filteredJobRows.map((row) => Object.values(row).join(","))].join("\n"),
                      "text/csv",
                    )
                  }
                  disabled={filteredJobRows.length === 0}
                >
                  Download CSV
                </button>
              </div>
            </div>
            <div className="filter-row">
              {availableStatuses.map((status) => (
                <label key={status}>
                  <input
                    type="checkbox"
                    checked={selectedStatuses.includes(status)}
                    onChange={(event) =>
                      setSelectedStatuses((current) =>
                        event.target.checked
                          ? [...current, status]
                          : current.filter((item) => item !== status),
                      )
                    }
                  />
                  {status}
                </label>
              ))}
            </div>
            {loading ? <p>Loading…</p> : null}
            {filteredJobRows.length === 0 ? (
              <p className="muted">No jobs match the selected filters.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Title</th>
                    <th>Status</th>
                    <th>Age</th>
                    <th>Time in Status</th>
                    <th>Assigned Worker ID</th>
                    <th>Time Since Checkpoint</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredJobRows.map((job) => (
                    <tr className={JOB_STATUS_COLORS[job.status] || ""} key={job.job_id + job.title}>
                      <td>{job.job_id}</td>
                      <td>{job.title}</td>
                      <td>{job.status}</td>
                      <td>{job.age}</td>
                      <td>{job.time_in_status}</td>
                      <td>{job.assigned_worker_id}</td>
                      <td>{job.time_since_checkpoint}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {jobs.length > 0 ? (
              <div className="details-panel">
                <h3>Job details</h3>
                <select value={selectedJobId} onChange={(event) => setSelectedJobId(event.target.value)}>
                  {jobs.map((job) => (
                    <option key={job.id} value={job.id}>
                      {job.title} [{job.status}]
                    </option>
                  ))}
                </select>
                {selectedJob ? (
                  <dl className="detail-grid">
                    <div>
                      <dt>Job ID</dt>
                      <dd>{selectedJob.id}</dd>
                    </div>
                    <div>
                      <dt>Assigned Worker ID</dt>
                      <dd>{selectedJob.assigned_worker_id || "-"}</dd>
                    </div>
                    <div>
                      <dt>Created at</dt>
                      <dd>{parseDate(selectedJob.created_at)?.toISOString() || "-"}</dd>
                    </div>
                    <div>
                      <dt>Input bundle path</dt>
                      <dd>{selectedJob.input_bundle_path}</dd>
                    </div>
                    <div>
                      <dt>Latest checkpoint path</dt>
                      <dd>{selectedJob.latest_checkpoint_path || "-"}</dd>
                    </div>
                    <div>
                      <dt>Last checkpoint at</dt>
                      <dd>{parseDate(selectedJob.last_checkpoint_at)?.toISOString() || "-"}</dd>
                    </div>
                  </dl>
                ) : null}
              </div>
            ) : null}
          </section>
        ) : null}

        {activeTab === "workers" ? (
          <section className="card">
            <div className="section-header">
              <h2>Workers</h2>
              <div className="button-row">
                <button onClick={() => copyText(toDelimited(workerRows))}>Copy TSV</button>
                <button
                  className="secondary"
                  onClick={() =>
                    downloadText(
                      "relaymd-workers.csv",
                      [Object.keys(workerRows[0] ?? {}).join(","), ...workerRows.map((row) => Object.values(row).join(","))].join("\n"),
                      "text/csv",
                    )
                  }
                  disabled={workerRows.length === 0}
                >
                  Download CSV
                </button>
              </div>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Platform</th>
                  <th>GPU</th>
                  <th>Provider ID</th>
                  <th>Provider State</th>
                  <th>Uptime</th>
                  <th>Last Heartbeat</th>
                  <th>Current Job</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {workerRows.map((worker) => (
                  <tr className={`worker-${worker.status}`} key={`${worker.platform}-${worker.provider_id}`}>
                    <td>{worker.platform}</td>
                    <td>{worker.gpu}</td>
                    <td>{worker.provider_id}</td>
                    <td>{worker.provider_state}</td>
                    <td>{worker.uptime}</td>
                    <td>{worker.last_heartbeat}</td>
                    <td>{worker.current_job}</td>
                    <td>{worker.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ) : null}

        {activeTab === "clusters" ? (
          <section className="card">
            <h2>Cluster Configs</h2>
            {clusters.length === 0 ? (
              <p className="muted">No cluster configs available.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Partition</th>
                    <th>Strategy</th>
                    <th>Max Pending Jobs</th>
                    <th>Wall Time</th>
                  </tr>
                </thead>
                <tbody>
                  {clusters.map((cluster) => (
                    <tr key={cluster.name}>
                      <td>{cluster.name}</td>
                      <td>{cluster.partition}</td>
                      <td>{cluster.strategy}</td>
                      <td>{cluster.max_pending_jobs}</td>
                      <td>{cluster.wall_time}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        ) : null}
      </main>
    </div>
  );
}
