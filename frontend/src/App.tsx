import { useEffect, useMemo, useState } from "react";

import { cancelJob, fetchDashboardData, fetchFrontendConfig, requeueJob } from "./api";
import { AppShell } from "./components/AppShell";
import { MetricStrip } from "./components/MetricStrip";
import { buildJobRows, buildWorkerRows, formatDuration, toCsv, toDelimited } from "./format";
import { clearApiToken, loadApiToken, saveApiToken } from "./storage";
import type { DashboardPayload, FrontendConfig, JobRead } from "./types";
import { ClustersView } from "./views/ClustersView";
import { JobsView } from "./views/JobsView";
import { SettingsView } from "./views/SettingsView";
import { WorkersView } from "./views/WorkersView";

type ViewName = "jobs" | "workers" | "clusters" | "settings";

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
  const [activeView, setActiveView] = useState<ViewName>("jobs");
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
  const availableStatuses = useMemo(() => Array.from(new Set(jobRows.map((job) => job.status))).sort(), [jobRows]);

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
    if (trimmed) {
      setActiveView("jobs");
    }
  };

  const resetToken = () => {
    clearApiToken();
    setTokenInput("");
    setToken("");
    setData(null);
    setActionMessage("");
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

  const navigation = [
    { id: "jobs", label: "Jobs", description: "Queue, detail, and actions" },
    { id: "workers", label: "Workers", description: "Fleet health and assignments" },
    { id: "clusters", label: "Clusters", description: "Provisioning targets" },
    { id: "settings", label: "Settings", description: "Token and runtime config" },
  ] satisfies Array<{ id: ViewName; label: string; description: string }>;

  const header = (
    <header className="console-header">
      <div>
        <p className="eyebrow">Operational Console</p>
        <h2>{navigation.find((item) => item.id === activeView)?.label}</h2>
        <p className="header-copy">
          Orchestrator: {config?.api_base_url || window.location.origin} | Refresh:{" "}
          {config?.refresh_interval_seconds ?? "-"}s
        </p>
      </div>
      {!token ? (
        <button className="secondary" onClick={() => setActiveView("settings")}>
          Configure token
        </button>
      ) : null}
    </header>
  );

  const overview = (
    <>
      <section className="signal-strip">
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
          <div className="banner warning">
            API token missing. Open Settings to store a token and enable dashboard data.
          </div>
        ) : null}
        {error && offlineSince ? (
          <div className="banner error">
            Orchestrator unreachable. Offline for {formatDuration((Date.now() - offlineSince) / 1000)}.
          </div>
        ) : null}
      </section>

      <MetricStrip
        items={[
          { label: "Queued", value: statusCounts.queued ?? 0 },
          { label: "Running", value: statusCounts.running ?? 0, tone: "accent" },
          { label: "Completed", value: statusCounts.completed ?? 0, tone: "success" },
          { label: "Failed", value: statusCounts.failed ?? 0, tone: "danger" },
          { label: "Cancelled", value: statusCounts.cancelled ?? 0 },
          { label: "Active Workers", value: activeWorkers, tone: "accent" },
          { label: "Provisioning", value: provisioningWorkers },
        ]}
      />
    </>
  );

  return (
    <AppShell
      activeView={activeView}
      navigation={navigation}
      onNavigate={setActiveView}
      header={header}
      overview={overview}
    >
      {pendingCancelJob ? (
        <section className="panel confirm-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Confirmation Required</p>
              <h2>Cancel {pendingCancelJob.title}?</h2>
              <p className="panel-copy">This cannot be undone. Workers will stop on their next poll cycle.</p>
            </div>
          </div>
          <div className="toolbar">
            <button className="danger-ghost" onClick={() => void handleCancel(pendingCancelJob)}>
              Confirm cancellation
            </button>
            <button className="secondary" onClick={() => setPendingCancelJob(null)}>
              Abort
            </button>
          </div>
        </section>
      ) : null}

      {activeView === "jobs" ? (
        <JobsView
          jobs={jobs}
          rows={jobRows}
          selectedJobId={selectedJobId}
          selectedStatuses={selectedStatuses}
          onSelectJob={setSelectedJobId}
          onToggleStatus={(status, nextChecked) =>
            setSelectedStatuses((current) =>
              nextChecked ? [...current, status] : current.filter((item) => item !== status),
            )
          }
          onCopyExport={copyText}
          onDownloadExport={downloadText}
          onCancelJob={setPendingCancelJob}
          onRequeueJob={(job) => void handleRequeue(job)}
          loading={loading}
        />
      ) : null}

      {activeView === "workers" ? (
        <WorkersView
          rows={workerRows}
          onCopyExport={copyText}
          onDownloadExport={downloadText}
          toDelimited={toDelimited}
          toCsv={toCsv}
        />
      ) : null}

      {activeView === "clusters" ? <ClustersView clusters={clusters} /> : null}

      {activeView === "settings" ? (
        <SettingsView
          tokenInput={tokenInput}
          tokenStored={Boolean(token)}
          apiBaseUrl={config?.api_base_url || window.location.origin}
          refreshIntervalSeconds={config?.refresh_interval_seconds ?? "-"}
          onTokenChange={setTokenInput}
          onSaveToken={saveToken}
          onClearToken={resetToken}
        />
      ) : null}
    </AppShell>
  );
}
