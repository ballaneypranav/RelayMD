import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, Boxes, BriefcaseBusiness, RefreshCw, Settings, Wifi, WifiOff } from "lucide-react";
import type { LucideIcon } from "lucide-react";

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
const ACTIVE_JOB_STATUSES = new Set(["queued", "assigned", "running", "handoff", "cancelling"]);
const JOB_HISTORY_REFRESH_MS = 30_000;

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
  const [pendingCancelJobs, setPendingCancelJobs] = useState<JobRead[]>([]);
  const [actionMessage, setActionMessage] = useState<string>("");
  const [actionError, setActionError] = useState<string>("");
  const [clusterEdits, setClusterEdits] = useState<Record<string, boolean>>({});
  const [saveClusterEditsInFlight, setSaveClusterEditsInFlight] = useState(false);
  const [jobHistoryById, setJobHistoryById] = useState<Record<string, JobHistoryRead>>({});
  const historyInFlightRef = useRef<Set<string>>(new Set());
  const jobHistoryFetchedAtRef = useRef<Record<string, number>>({});

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
    const visibleJobIds = new Set(jobs.map((job) => job.id));
    setJobHistoryById((previous) =>
      Object.fromEntries(Object.entries(previous).filter(([jobId]) => visibleJobIds.has(jobId))),
    );
    jobHistoryFetchedAtRef.current = Object.fromEntries(
      Object.entries(jobHistoryFetchedAtRef.current).filter(([jobId]) => visibleJobIds.has(jobId)),
    );
  }, [jobs]);

  useEffect(() => {
    if (!config) {
      return;
    }
    const now = Date.now();
    for (const job of jobs) {
      const isActiveJob = ACTIVE_JOB_STATUSES.has(job.status);
      const hasCachedHistory = Boolean(jobHistoryById[job.id]);
      const lastFetchedAt = jobHistoryFetchedAtRef.current[job.id] ?? 0;
      const isFresh = now - lastFetchedAt < JOB_HISTORY_REFRESH_MS;
      if (
        historyInFlightRef.current.has(job.id) ||
        (hasCachedHistory && (!isActiveJob || isFresh))
      ) {
        continue;
      }
      historyInFlightRef.current.add(job.id);
      void fetchJobHistory(config.api_base_url, job.id)
        .then((history) => {
          setJobHistoryById((previous) => ({ ...previous, [job.id]: history }));
          jobHistoryFetchedAtRef.current[job.id] = Date.now();
        })
        .catch(() => {
          // Keep missing history absent; UI falls back when needed.
        })
        .finally(() => {
          historyInFlightRef.current.delete(job.id);
        });
    }
  }, [config, jobs, jobHistoryById]);

  const selectedJobHistory = selectedJobId ? (jobHistoryById[selectedJobId] ?? null) : null;

  const statusCounts = jobs.reduce<Record<string, number>>((counts, job) => {
    counts[job.status] = (counts[job.status] ?? 0) + 1;
    return counts;
  }, {});
  const blockedCount = jobs.filter((job) => job.status === "queued" && job.queue_blocked_reason).length;

  const activeWorkers = workers.filter((worker) => worker.status !== "queued").length;
  const provisioningWorkers = workers.filter((worker) => worker.status === "queued").length;

  const handleCancelJobs = async (jobsToCancel: JobRead[]) => {
    if (!config) {
      return;
    }
    try {
      const results = await Promise.allSettled(jobsToCancel.map((job) => cancelJob(config.api_base_url, job.id)));
      const succeeded = results.filter((r) => r.status === "fulfilled").length;
      const failed = results.filter((r) => r.status === "rejected") as PromiseRejectedResult[];

      if (succeeded > 0) {
        setActionMessage(succeeded === 1 ? "Job cancelled" : `${succeeded} jobs cancelled`);
        setPendingCancelJobs([]);
        setError("");
      } else {
        setActionMessage("");
      }

      if (failed.length > 0) {
        const firstError = failed[0].reason;
        setActionError(firstError instanceof Error ? firstError.message : String(firstError));
      } else {
        setActionError("");
      }

      if (succeeded > 0) {
        const payload = await fetchDashboardData(config.api_base_url);
        setData(payload);
      }
    } catch (actionFailure) {
      setActionError(actionFailure instanceof Error ? actionFailure.message : String(actionFailure));
      setActionMessage("");
    }
  };

  const handleBulkRequeue = async (jobsToRequeue: JobRead[]) => {
    if (!config) {
      return;
    }
    try {
      const results = await Promise.allSettled(jobsToRequeue.map((job) => requeueJob(config.api_base_url, job.id)));
      const successes = results.filter((r) => r.status === "fulfilled") as PromiseFulfilledResult<string>[];
      const failures = results.filter((r) => r.status === "rejected") as PromiseRejectedResult[];

      if (successes.length > 0) {
        setActionMessage(
          successes.length === 1
            ? `Re-queued as job ${successes[0].value}`
            : `Re-queued ${successes.length} jobs`,
        );
      } else {
        setActionMessage("");
      }

      if (failures.length > 0) {
        const firstError = failures[0].reason;
        setActionError(firstError instanceof Error ? firstError.message : String(firstError));
      } else {
        setActionError("");
      }

      if (successes.length > 0) {
        const payload = await fetchDashboardData(config.api_base_url);
        setData(payload);
      }
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
    { id: "jobs", label: "Jobs", description: "Queue, detail, and actions", icon: BriefcaseBusiness },
    { id: "workers", label: "Workers", description: "Fleet health and assignments", icon: Activity },
    { id: "clusters", label: "Clusters", description: "Provisioning targets", icon: Boxes },
    { id: "settings", label: "Settings", description: "Proxy auth and runtime config", icon: Settings },
  ] satisfies Array<{ id: ViewName; label: string; description: string; icon: LucideIcon }>;

  const header = (
    <header className="console-header">
      <div>
        <div className="header-title-row">
          <p className="eyebrow">RelayMD</p>
          <span>Operator Console</span>
        </div>
        <h2>{navigation.find((item) => item.id === activeView)?.label}</h2>
        <p className="header-copy">
          {lastUpdatedAt ? `Last updated ${new Date(lastUpdatedAt).toLocaleTimeString()}` : "Last updated -"}
        </p>
      </div>
      <div className="console-header-actions">
        <div className="meta-pill meta-pill-version">RelayMD v{health?.version ?? "-"}</div>
        <div className={error ? "meta-pill meta-pill-error" : "meta-pill meta-pill-live"}>
          {error ? <WifiOff aria-hidden="true" size={15} /> : <Wifi aria-hidden="true" size={15} />}
          {error ? "Error" : "Live"}
        </div>
        <button className="secondary header-action-button" onClick={() => void refreshData()} disabled={isRefreshing}>
          <RefreshCw aria-hidden="true" size={16} className={isRefreshing ? "spin-icon" : undefined} />
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
      {pendingCancelJobs.length > 0 ? (
        <section className="panel confirm-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Confirmation Required</p>
              <h2>
                {pendingCancelJobs.length === 1
                  ? `Cancel ${pendingCancelJobs[0].title}?`
                  : `Cancel ${pendingCancelJobs.length} jobs?`}
              </h2>
              <p className="panel-copy">
                This cannot be undone. Workers will stop on their next poll cycle.
              </p>
            </div>
          </div>
          <div className="toolbar">
            <button className="danger-ghost" onClick={() => void handleCancelJobs(pendingCancelJobs)}>
              Confirm cancellation
            </button>
            <button className="secondary" onClick={() => setPendingCancelJobs([])}>
              Abort
            </button>
          </div>
        </section>
      ) : null}

      {activeView === "jobs" ? (
        <JobsView
          jobs={jobs}
          jobHistoryById={jobHistoryById}
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
          onCancelJob={(job) => setPendingCancelJobs([job])}
          onBulkCancelJobs={setPendingCancelJobs}
          onRequeueJob={(job) => void handleRequeue(job)}
          onBulkRequeueJobs={(jobsToRequeue) => void handleBulkRequeue(jobsToRequeue)}
          loading={loading}
          selectedJobHistory={selectedJobHistory}
        />
      ) : null}

      {activeView === "workers" ? (
        <WorkersView
          workers={workers}
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
