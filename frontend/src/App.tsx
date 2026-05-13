import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { cancelJob, fetchDashboardData, fetchFrontendConfig, fetchJobHistory, requeueJob, updateClusterProvisioningEnabledMap } from "./api";
import { AppShell } from "./components/AppShell";
import { MetricStrip } from "./components/MetricStrip";
import { StatusPill } from "./components/StatusPill";
import { buildJobRows, buildWorkerRows, formatDuration, toCsv, toDelimited } from "./format";
import type { DashboardPayload, FrontendConfig, JobHistoryRead, JobRead } from "./types";
import { ClustersView } from "./views/ClustersView";
import { JobsView } from "./views/JobsView";
import { SettingsView } from "./views/SettingsView";
import { WorkersView } from "./views/WorkersView";

type ViewName = "jobs" | "workers" | "clusters" | "settings";
const DEFAULT_VIEW: ViewName = "jobs";
const APP_BASE_PATH = "/app";

const PATH_TO_VIEW: Record<string, ViewName> = {
  "/app/jobs": "jobs",
  "/app/workers": "workers",
  "/app/clusters": "clusters",
  "/app/settings": "settings",
};

function viewToPath(view: ViewName): string {
  return `${APP_BASE_PATH}/${view}`;
}

function parseViewFromPath(pathname: string): ViewName | null {
  return PATH_TO_VIEW[pathname] ?? null;
}

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

function useDashboardData(config: FrontendConfig | null) {
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [offlineSince, setOfflineSince] = useState<number | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const [lastRefreshError, setLastRefreshError] = useState<string>("");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const inFlightRef = useRef(false);

  const refreshData = useCallback(async () => {
    if (!config || inFlightRef.current) {
      return;
    }
    inFlightRef.current = true;
    setIsRefreshing(true);
    try {
      const payload = await fetchDashboardData(config.api_base_url);
      setData(payload);
      setError("");
      setLastRefreshError("");
      setOfflineSince(null);
      setLastUpdatedAt(Date.now());
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : String(loadError);
      setError(message);
      setLastRefreshError(message);
      setOfflineSince((previous) => previous ?? Date.now());
    } finally {
      setLoading(false);
      setIsRefreshing(false);
      inFlightRef.current = false;
    }
  }, [config]);

  useEffect(() => {
    if (!config) {
      setLoading(false);
      return;
    }

    void refreshData();
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "hidden") {
        return;
      }
      void refreshData();
    }, config.refresh_interval_seconds * 1000);

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void refreshData();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [config, refreshData]);

  return {
    data,
    error,
    loading,
    offlineSince,
    lastUpdatedAt,
    lastRefreshError,
    isRefreshing,
    refreshData,
    setData,
    setError,
  };
}

export function App() {
  const [config, setConfig] = useState<FrontendConfig | null>(null);
  const [configError, setConfigError] = useState("");
  const [activeView, setActiveView] = useState<ViewName>(() => parseViewFromPath(window.location.pathname) ?? DEFAULT_VIEW);
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string>("");
  const [pendingCancelJob, setPendingCancelJob] = useState<JobRead | null>(null);
  const [actionMessage, setActionMessage] = useState<string>("");
  const [actionError, setActionError] = useState<string>("");
  const [clusterEdits, setClusterEdits] = useState<Record<string, boolean>>({});
  const [saveClusterEditsInFlight, setSaveClusterEditsInFlight] = useState(false);
  const [selectedJobHistory, setSelectedJobHistory] = useState<JobHistoryRead | null>(null);
  const historyRequestSeqRef = useRef(0);

  const { data, error, loading, offlineSince, lastUpdatedAt, lastRefreshError, isRefreshing, refreshData, setData, setError } =
    useDashboardData(config);

  useEffect(() => {
    void fetchFrontendConfig()
      .then(setConfig)
      .catch((loadError) => {
        setConfigError(loadError instanceof Error ? loadError.message : String(loadError));
      });
  }, []);

  useEffect(() => {
    const currentView = parseViewFromPath(window.location.pathname);
    if (!currentView) {
      window.history.replaceState(null, "", viewToPath(DEFAULT_VIEW));
      setActiveView(DEFAULT_VIEW);
      return;
    }
    setActiveView(currentView);

    const onPopState = () => {
      const nextView = parseViewFromPath(window.location.pathname) ?? DEFAULT_VIEW;
      setActiveView(nextView);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigateToView = (view: ViewName) => {
    const targetPath = viewToPath(view);
    if (window.location.pathname !== targetPath) {
      window.history.pushState(null, "", targetPath);
    }
    setActiveView(view);
  };

  const now = useMemo(() => new Date(), [data, error]);
  const jobs = data?.jobs ?? [];
  const workers = data?.workers ?? [];
  const clusters = data?.clusters ?? [];
  const health = data?.health;
  const clusterEditCount = useMemo(
    () => clusters.filter((cluster) => (clusterEdits[cluster.name] ?? cluster.enabled) !== cluster.enabled).length,
    [clusterEdits, clusters],
  );

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

  useEffect(() => {
    if (!config || !selectedJobId) {
      historyRequestSeqRef.current += 1;
      setSelectedJobHistory(null);
      return;
    }
    const requestSeq = historyRequestSeqRef.current + 1;
    historyRequestSeqRef.current = requestSeq;
    void fetchJobHistory(config.api_base_url, selectedJobId)
      .then((history) => {
        if (historyRequestSeqRef.current !== requestSeq) {
          return;
        }
        setSelectedJobHistory(history);
      })
      .catch(() => {
        if (historyRequestSeqRef.current !== requestSeq) {
          return;
        }
        setSelectedJobHistory(null);
      });
  }, [config, selectedJobId]);

  const statusCounts = jobs.reduce<Record<string, number>>((counts, job) => {
    counts[job.status] = (counts[job.status] ?? 0) + 1;
    return counts;
  }, {});
  const blockedCount = jobs.filter((job) => job.status === "queued" && job.queue_blocked_reason).length;

  const activeWorkers = workers.filter((worker) => worker.status !== "queued").length;
  const provisioningWorkers = workers.filter((worker) => worker.status === "queued").length;

  const handleCancel = async (job: JobRead) => {
    if (!config) {
      return;
    }
    try {
      await cancelJob(config.api_base_url, job.id);
      setActionMessage("Job cancelled");
      setActionError("");
      setPendingCancelJob(null);
      setError("");
      const payload = await fetchDashboardData(config.api_base_url);
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
      const newJobId = await requeueJob(config.api_base_url, job.id);
      setActionMessage(`Re-queued as job ${newJobId}`);
      setActionError("");
      const payload = await fetchDashboardData(config.api_base_url);
      setData(payload);
    } catch (actionFailure) {
      setActionError(actionFailure instanceof Error ? actionFailure.message : String(actionFailure));
      setActionMessage("");
    }
  };

  const handleClusterToggle = (clusterName: string, enabled: boolean) => {
    setClusterEdits((current) => ({ ...current, [clusterName]: enabled }));
  };

  const handleSaveClusterEdits = async () => {
    if (!config || clusterEditCount === 0) {
      return;
    }
    setSaveClusterEditsInFlight(true);
    try {
      const enabledMap = Object.fromEntries(
        clusters.map((cluster) => [cluster.name, clusterEdits[cluster.name] ?? cluster.enabled]),
      );
      await updateClusterProvisioningEnabledMap(config.api_base_url, enabledMap);
      const payload = await fetchDashboardData(config.api_base_url);
      setData(payload);
      setClusterEdits({});
      setActionMessage("Cluster provisioning settings updated");
      setActionError("");
    } catch (actionFailure) {
      setActionError(actionFailure instanceof Error ? actionFailure.message : String(actionFailure));
      setActionMessage("");
    } finally {
      setSaveClusterEditsInFlight(false);
    }
  };

  if (configError) {
    return <div className="error-panel">Frontend config failed to load: {configError}</div>;
  }

  const navigation = [
    { id: "jobs", label: "Jobs", description: "Queue, detail, and actions" },
    { id: "workers", label: "Workers", description: "Fleet health and assignments" },
    { id: "clusters", label: "Clusters", description: "Provisioning targets" },
    { id: "settings", label: "Settings", description: "Proxy auth and runtime config" },
  ] satisfies Array<{ id: ViewName; label: string; description: string }>;

  const header = (
    <header className="console-header">
      <div>
        <p className="eyebrow">Operational Console</p>
        <h2>{navigation.find((item) => item.id === activeView)?.label}</h2>
        <p className="header-copy">
          {lastUpdatedAt ? `Last updated ${new Date(lastUpdatedAt).toLocaleTimeString()}` : "Last updated -"}
        </p>
      </div>
      <div className="console-header-actions">
        <div className="meta-pill meta-pill-version">RelayMD v{health?.version ?? "-"}</div>
        <div className={error ? "meta-pill meta-pill-error" : "meta-pill meta-pill-live"}>{error ? "Error" : "Live"}</div>
        <button className="secondary header-action-button" onClick={() => void refreshData()} disabled={isRefreshing}>
          {isRefreshing ? "Refreshing..." : "Refresh"}
        </button>
        {health?.tailscale ? (
          health.tailscale.connected ? (
            <button className="connection-pill-button" onClick={() => navigateToView("settings")}>
              <StatusPill className="connection-pill" tone="completed">
                CONNECTED
              </StatusPill>
            </button>
          ) : (
            <button className="connection-pill-button" onClick={() => navigateToView("settings")}>
              <StatusPill className="connection-pill" tone="failed">
                Connection error
              </StatusPill>
            </button>
          )
        ) : null}
      </div>
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
        {actionMessage ? <div className="banner success">{actionMessage}</div> : null}
        {actionError ? <div className="banner error">{actionError}</div> : null}
        {error && offlineSince ? (
          <div className="banner error">
            Orchestrator unreachable. Offline for {formatDuration((Date.now() - offlineSince) / 1000)}.
          </div>
        ) : null}
        {lastRefreshError ? <div className="banner warning">Latest refresh failed: {lastRefreshError}</div> : null}
      </section>

      <section className="overview-groups" aria-label="System overview">
        <section className="overview-group">
          <div className="overview-group-header">
            <p className="eyebrow">Jobs</p>
            <h3>Job states</h3>
          </div>
          <MetricStrip
            ariaLabel="Job metrics"
            items={[
              { label: "Queued", value: statusCounts.queued ?? 0 },
              { label: "Blocked", value: blockedCount, tone: "danger" },
              { label: "Running", value: statusCounts.running ?? 0, tone: "accent" },
              { label: "Completed", value: statusCounts.completed ?? 0, tone: "success" },
              { label: "Failed", value: statusCounts.failed ?? 0, tone: "danger" },
              { label: "Cancelled", value: statusCounts.cancelled ?? 0 },
            ]}
          />
        </section>

        <section className="overview-group">
          <div className="overview-group-header">
            <p className="eyebrow">Workers</p>
            <h3>Worker states</h3>
          </div>
          <MetricStrip
            ariaLabel="Worker metrics"
            items={[
              { label: "Active", value: activeWorkers, tone: "accent" },
              { label: "Provisioning", value: provisioningWorkers },
            ]}
          />
        </section>
      </section>
    </>
  );

  return (
    <AppShell
      activeView={activeView}
      navigation={navigation}
      onNavigate={navigateToView}
      header={header}
      overview={overview}
    >
      {pendingCancelJob ? (
        <section className="panel confirm-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Confirmation Required</p>
              <h2>Cancel {pendingCancelJob.title}?</h2>
              <p className="panel-copy">
                This cannot be undone. Workers will stop on their next poll cycle.
              </p>
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
          selectedJobHistory={selectedJobHistory}
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

      {activeView === "clusters" ? (
        <ClustersView
          clusters={clusters}
          clusterEdits={clusterEdits}
          unsavedCount={clusterEditCount}
          saveInFlight={saveClusterEditsInFlight}
          onToggle={handleClusterToggle}
          onSave={() => void handleSaveClusterEdits()}
        />
      ) : null}

      {activeView === "settings" ? (
        <SettingsView
          apiBaseUrl={config?.api_base_url || window.location.origin}
          refreshIntervalSeconds={config?.refresh_interval_seconds ?? "-"}
        />
      ) : null}
    </AppShell>
  );
}
