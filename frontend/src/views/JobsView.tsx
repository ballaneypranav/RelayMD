import { useMemo } from "react";
import type { ColumnDef, Row } from "@tanstack/react-table";

import {
  etaSeconds,
  formatDuration,
  parseDate,
  toCsv,
  toDelimited,
  totalRuntimeSeconds,
  type JobRow,
} from "../format";
import { ConsoleTable, type ConsoleTableToolbarContext } from "../components/ConsoleTable";
import { StatusPill } from "../components/StatusPill";
import type { JobHistoryRead, JobRead } from "../types";

const BLOCKED_REASON_LABELS: Record<string, string> = {
  no_enabled_pinned_clusters: "Pinned clusters disabled",
  no_matching_pinned_clusters: "Pinned clusters unavailable",
};

const BULK_CANCEL_STATUSES = new Set(["queued", "assigned", "running"]);
const BULK_REQUEUE_STATUSES = new Set(["failed", "cancelled"]);

interface JobTableRow extends JobRow {
  job: JobRead;
  job_id_full: string;
  assigned_worker_full: string;
  created_at_iso: string;
  assigned_at_iso: string;
  started_at_iso: string;
  status_changed_at_iso: string;
  runtime: string;
  etc: string;
  updated_at_iso: string;
  input_bundle: string;
  pinned_clusters: string;
  comment_text: string;
  queue_blocked: string;
  progress_percent: string;
  progress_codes_text: string;
  latest_checkpoint: string;
  checkpoint_cycle_status_text: string;
  checkpoint_failures_text: string;
  history_source: string;
  checkpoint_age: string;
}

interface JobsViewProps {
  jobs: JobRead[];
  rows: JobRow[];
  selectedJobId: string;
  selectedStatuses: string[];
  onSelectJob: (jobId: string) => void;
  onToggleStatus: (status: string, nextChecked: boolean) => void;
  onCopyExport: (text: string) => void;
  onDownloadExport: (filename: string, text: string, mime: string) => void;
  onCancelJob: (job: JobRead) => void;
  onBulkCancelJobs: (jobs: JobRead[]) => void;
  onRequeueJob: (job: JobRead) => void;
  onBulkRequeueJobs: (jobs: JobRead[]) => void;
  loading: boolean;
  selectedJobHistory: JobHistoryRead | null;
}

function canCancel(job: JobRead): boolean {
  return BULK_CANCEL_STATUSES.has(job.status);
}

function canRequeue(job: JobRead): boolean {
  return BULK_REQUEUE_STATUSES.has(job.status);
}

function formatCheckpointAge(job: JobRead): string {
  const checkpointAt = parseDate(job.last_checkpoint_at);
  return checkpointAt ? formatDuration((Date.now() - checkpointAt.getTime()) / 1000) : "-";
}

function JobExpandedDetails({
  row,
  selectedJobHistory,
}: {
  row: JobTableRow;
  selectedJobHistory: JobHistoryRead | null;
}) {
  const job = row.job;
  const now = new Date();
  const runtimeSeconds = totalRuntimeSeconds(job, now, selectedJobHistory?.worker_segments);
  const eta = etaSeconds(job, now, selectedJobHistory?.worker_segments);

  return (
    <div className="job-expanded-detail">
      <dl className="detail-list job-detail-grid">
        <div>
          <dt>Job ID</dt>
          <dd>{job.id}</dd>
        </div>
        <div>
          <dt>Assigned Worker</dt>
          <dd>{job.assigned_worker_id || "-"}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{parseDate(job.created_at)?.toISOString() ?? "-"}</dd>
        </div>
        <div>
          <dt>Assigned</dt>
          <dd>{parseDate(job.assigned_at)?.toISOString() ?? "-"}</dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{parseDate(job.started_at)?.toISOString() ?? "-"}</dd>
        </div>
        <div>
          <dt>Status Changed</dt>
          <dd>{parseDate(job.status_changed_at)?.toISOString() ?? "-"}</dd>
        </div>
        <div>
          <dt>Total Runtime</dt>
          <dd>{formatDuration(runtimeSeconds)}</dd>
        </div>
        <div>
          <dt>ETC</dt>
          <dd>{eta !== null ? formatDuration(eta) : "-"}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{parseDate(job.updated_at)?.toISOString() ?? "-"}</dd>
        </div>
        <div>
          <dt>Input Bundle</dt>
          <dd>{job.input_bundle_path}</dd>
        </div>
        <div>
          <dt>Pinned Clusters</dt>
          <dd>
            {(job.preferred_clusters ?? []).length > 0 ? (job.preferred_clusters ?? []).join(", ") : "-"}
          </dd>
        </div>
        <div>
          <dt>Comment</dt>
          <dd style={{ whiteSpace: "pre-wrap" }}>{job.comment || "-"}</dd>
        </div>
        <div>
          <dt>Queue Blocked</dt>
          <dd>
            {job.status === "queued" && job.queue_blocked_reason
              ? (BLOCKED_REASON_LABELS[job.queue_blocked_reason] ?? job.queue_blocked_reason)
              : "-"}
          </dd>
        </div>
        <div>
          <dt>Progress</dt>
          <dd>{Math.round(((job.progress ?? 0) * 100) * 10) / 10}%</dd>
        </div>
        <div>
          <dt>Progress Codes</dt>
          <dd>{(job.progress_codes ?? []).length > 0 ? (job.progress_codes ?? []).join(", ") : "-"}</dd>
        </div>
        <div>
          <dt>Latest Checkpoint</dt>
          <dd>{job.latest_checkpoint_manifest_path || job.latest_checkpoint_path || "-"}</dd>
        </div>
        <div>
          <dt>Checkpoint Cycle Status</dt>
          <dd>{job.checkpoint_cycle_status || "-"}</dd>
        </div>
        <div>
          <dt>Checkpoint Failures</dt>
          <dd>
            {(job.checkpoint_cycle_failures ?? []).length > 0
              ? (job.checkpoint_cycle_failures ?? [])
                  .map((failure) => `${failure.code}: ${failure.detail}`)
                  .join("; ")
              : "-"}
          </dd>
        </div>
        <div>
          <dt>History Source</dt>
          <dd>
            {!selectedJobHistory
              ? "Unavailable"
              : selectedJobHistory.derived
                ? "Derived fallback"
                : "Persisted events"}
          </dd>
        </div>
        <div>
          <dt>Checkpoint Age</dt>
          <dd>{formatCheckpointAge(job)}</dd>
        </div>
      </dl>

      <div className="job-history-grid">
        <section>
          <h3>Worker Runtime Totals</h3>
          {selectedJobHistory && selectedJobHistory.worker_totals.length > 0 ? (
            <ul>
              {selectedJobHistory.worker_totals.map((total) => (
                <li key={`${total.worker_id || "none"}-${total.segment_count}`}>
                  {(total.worker_id || "unassigned").slice(0, 12)}:{" "}
                  {formatDuration(total.total_runtime_seconds)} ({total.segment_count} segments)
                </li>
              ))}
            </ul>
          ) : (
            <p className="panel-copy">No runtime segments yet.</p>
          )}
        </section>

        <section>
          <h3>Timeline</h3>
          {selectedJobHistory && selectedJobHistory.events.length > 0 ? (
            <ul>
              {selectedJobHistory.events.map((event) => (
                <li key={`${event.occurred_at}-${event.event_seq}`}>
                  {parseDate(event.occurred_at)?.toISOString() ?? event.occurred_at} - {event.event_type}
                  {event.worker_id ? ` (${event.worker_id.slice(0, 12)})` : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p className="panel-copy">No history events available.</p>
          )}
        </section>
      </div>
    </div>
  );
}

function JobsToolbar({
  context,
  filteredRows,
  onBulkCancelJobs,
  onBulkRequeueJobs,
  onCopyExport,
  onDownloadExport,
}: {
  context: ConsoleTableToolbarContext<JobTableRow>;
  filteredRows: JobRow[];
  onBulkCancelJobs: (jobs: JobRead[]) => void;
  onBulkRequeueJobs: (jobs: JobRead[]) => void;
  onCopyExport: (text: string) => void;
  onDownloadExport: (filename: string, text: string, mime: string) => void;
}) {
  const selectedJobs = context.selectedRows.map((row) => row.original.job);
  const hasSelection = selectedJobs.length > 0;
  const bulkCancelEnabled = hasSelection && selectedJobs.every(canCancel);
  const bulkRequeueEnabled = hasSelection && selectedJobs.every(canRequeue);

  const exportRows = context.table
    .getFilteredRowModel()
    .rows.map((row) => row.original)
    .map(({ job, latest_checkpoint, runtime, ...rest }) => rest);

  return (
    <>
      <button
        aria-label="Bulk cancel selected jobs"
        className="danger-ghost"
        disabled={!bulkCancelEnabled}
        onClick={() => onBulkCancelJobs(selectedJobs)}
        type="button"
      >
        Cancel
      </button>
      <button
        aria-label="Bulk requeue selected jobs"
        className="secondary"
        disabled={!bulkRequeueEnabled}
        onClick={() => onBulkRequeueJobs(selectedJobs)}
        type="button"
      >
        Requeue
      </button>
      <details className="table-menu">
        <summary>Export</summary>
        <div className="table-menu-panel">
          <button
            className="secondary"
            disabled={exportRows.length === 0}
            onClick={() => onCopyExport(toDelimited(exportRows))}
            type="button"
          >
            Copy TSV
          </button>
          <button
            className="secondary"
            disabled={exportRows.length === 0}
            onClick={() => onDownloadExport("relaymd-jobs.csv", toCsv(exportRows), "text/csv")}
            type="button"
          >
            Download CSV
          </button>
        </div>
      </details>
    </>
  );
}

export function JobsView({
  jobs,
  rows,
  selectedJobId,
  selectedStatuses,
  onSelectJob,
  onToggleStatus,
  onCopyExport,
  onDownloadExport,
  onCancelJob,
  onBulkCancelJobs,
  onRequeueJob,
  onBulkRequeueJobs,
  loading,
  selectedJobHistory,
}: JobsViewProps) {
  const availableStatuses = Array.from(new Set(rows.map((job) => job.status))).sort();
  const filteredRows =
    selectedStatuses.length > 0
      ? rows.filter((row) => selectedStatuses.includes(row.status))
      : rows;
  const jobById = useMemo(() => new Map(jobs.map((job) => [job.id, job])), [jobs]);
  const tableRows = useMemo<JobTableRow[]>(
    () =>
      filteredRows.flatMap((row) => {
        const job = jobById.get(row.id);
        if (!job) {
          return [];
        }
        return [
          {
            ...row,
            job,
            job_id_full: job.id,
            assigned_worker_full: job.assigned_worker_id || "-",
            created_at_iso: parseDate(job.created_at)?.toISOString() ?? "-",
            assigned_at_iso: parseDate(job.assigned_at)?.toISOString() ?? "-",
            started_at_iso: parseDate(job.started_at)?.toISOString() ?? "-",
            status_changed_at_iso: parseDate(job.status_changed_at)?.toISOString() ?? "-",
            latest_checkpoint: job.latest_checkpoint_manifest_path || job.latest_checkpoint_path || "-",
            runtime: formatDuration(totalRuntimeSeconds(job, new Date())),
            etc: (() => {
              const estimate = etaSeconds(job, new Date());
              return estimate !== null ? formatDuration(estimate) : "-";
            })(),
            updated_at_iso: parseDate(job.updated_at)?.toISOString() ?? "-",
            input_bundle: job.input_bundle_path,
            pinned_clusters:
              (job.preferred_clusters ?? []).length > 0 ? (job.preferred_clusters ?? []).join(", ") : "-",
            comment_text: job.comment || "-",
            queue_blocked:
              job.status === "queued" && job.queue_blocked_reason
                ? (BLOCKED_REASON_LABELS[job.queue_blocked_reason] ?? job.queue_blocked_reason)
                : "-",
            progress_percent: `${Math.round(((job.progress ?? 0) * 100) * 10) / 10}%`,
            progress_codes_text:
              (job.progress_codes ?? []).length > 0 ? (job.progress_codes ?? []).join(", ") : "-",
            checkpoint_cycle_status_text: job.checkpoint_cycle_status || "-",
            checkpoint_failures_text:
              (job.checkpoint_cycle_failures ?? []).length > 0
                ? (job.checkpoint_cycle_failures ?? [])
                    .map((failure) => `${failure.code}: ${failure.detail}`)
                    .join("; ")
                : "-",
            history_source: selectedJobHistory
              ? selectedJobHistory.derived
                ? "Derived fallback"
                : "Persisted events"
              : "Unavailable",
            checkpoint_age: formatCheckpointAge(job),
          },
        ];
      }),
    [filteredRows, jobById, selectedJobHistory],
  );

  const columns = useMemo<ColumnDef<JobTableRow>[]>(
    () => [
      {
        accessorKey: "title",
        header: "Title",
        cell: ({ row }) => (
          <button
            className="row-link"
            onClick={() => {
              onSelectJob(row.original.job.id);
              row.toggleExpanded(true);
            }}
            type="button"
          >
            <strong>{row.original.title}</strong>
          </button>
        ),
      },
      {
        accessorKey: "job_id",
        header: "Job",
      },
      {
        accessorKey: "job_id_full",
        header: "Job ID",
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <div className="cell-stack">
            <StatusPill tone={row.original.job.status}>{row.original.job.status}</StatusPill>
            {row.original.job.status === "queued" && row.original.job.queue_blocked_reason ? (
              <small>
                {BLOCKED_REASON_LABELS[row.original.job.queue_blocked_reason] ??
                  row.original.job.queue_blocked_reason}
              </small>
            ) : null}
          </div>
        ),
      },
      {
        accessorKey: "age",
        header: "Age",
      },
      {
        accessorKey: "time_in_status",
        header: "Time in Status",
      },
      {
        accessorKey: "assigned_worker_id",
        header: "Worker",
      },
      {
        accessorKey: "assigned_worker_full",
        header: "Assigned Worker",
      },
      {
        accessorKey: "created_at_iso",
        header: "Created",
      },
      {
        accessorKey: "assigned_at_iso",
        header: "Assigned",
      },
      {
        accessorKey: "started_at_iso",
        header: "Started",
      },
      {
        accessorKey: "status_changed_at_iso",
        header: "Status Changed",
      },
      {
        accessorKey: "time_since_checkpoint",
        header: "Checkpoint",
      },
      {
        accessorKey: "runtime",
        header: "Runtime",
      },
      {
        accessorKey: "etc",
        header: "ETC",
      },
      {
        accessorKey: "updated_at_iso",
        header: "Updated",
      },
      {
        accessorKey: "input_bundle",
        header: "Input Bundle",
      },
      {
        accessorKey: "pinned_clusters",
        header: "Pinned Clusters",
      },
      {
        accessorKey: "comment_text",
        header: "Comment",
      },
      {
        accessorKey: "queue_blocked",
        header: "Queue Blocked",
      },
      {
        accessorKey: "progress_percent",
        header: "Progress",
      },
      {
        accessorKey: "progress_codes_text",
        header: "Progress Codes",
      },
      {
        accessorKey: "latest_checkpoint",
        header: "Latest Checkpoint",
      },
      {
        accessorKey: "checkpoint_cycle_status_text",
        header: "Checkpoint Cycle Status",
      },
      {
        accessorKey: "checkpoint_failures_text",
        header: "Checkpoint Failures",
      },
      {
        accessorKey: "history_source",
        header: "History Source",
      },
      {
        accessorKey: "checkpoint_age",
        header: "Checkpoint Age",
      },
      {
        id: "actions",
        header: "Actions",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="inline-actions">
            {canCancel(row.original.job) ? (
              <button className="danger-ghost" onClick={() => onCancelJob(row.original.job)} type="button">
                Cancel
              </button>
            ) : null}
            {canRequeue(row.original.job) ? (
              <button className="secondary" onClick={() => onRequeueJob(row.original.job)} type="button">
                Requeue
              </button>
            ) : null}
          </div>
        ),
      },
    ],
    [onCancelJob, onRequeueJob, onSelectJob],
  );

  const selectedHistory =
    selectedJobId && selectedJobHistory ? selectedJobHistory : null;

  return (
    <section className="panel panel-table">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Jobs</p>
          <h2>Execution queue</h2>
          <p className="panel-copy">Search, filter, expand, and act on queued simulation work.</p>
        </div>
      </div>

      <ConsoleTable
        ariaLabel="Jobs"
        columns={columns}
        data={tableRows}
        emptyDescription="No jobs match the selected filters."
        emptyTitle="No jobs in view"
        enableSelection
        filterControls={
          <div className="filter-stack" aria-label="Job status filters">
            {availableStatuses.map((status) => (
              <label className="filter-chip" key={status}>
                <input
                  checked={selectedStatuses.includes(status)}
                  onChange={(event) => onToggleStatus(status, event.target.checked)}
                  type="checkbox"
                />
                <span>{status}</span>
              </label>
            ))}
          </div>
        }
        getRowId={(row) => row.id}
        initialPageSize={10}
        initialColumnVisibility={{
          assigned_worker_full: false,
          job_id_full: false,
          created_at_iso: false,
          assigned_at_iso: false,
          started_at_iso: false,
          status_changed_at_iso: false,
          etc: false,
          updated_at_iso: false,
          input_bundle: false,
          pinned_clusters: false,
          comment_text: false,
          queue_blocked: false,
          progress_percent: false,
          progress_codes_text: false,
          latest_checkpoint: false,
          checkpoint_cycle_status_text: false,
          checkpoint_failures_text: false,
          history_source: false,
          checkpoint_age: false,
        }}
        loading={loading}
        onExpandedRowToggle={(row: Row<JobTableRow>, nextExpanded) => {
          if (nextExpanded) {
            onSelectJob(row.original.job.id);
          }
        }}
        renderExpandedRow={(row) => (
          <JobExpandedDetails
            row={row.original}
            selectedJobHistory={selectedJobId === row.original.job.id ? selectedHistory : null}
          />
        )}
        searchPlaceholder="Search jobs"
        toolbarActions={(context) => (
          <JobsToolbar
            context={context}
            filteredRows={filteredRows}
            onBulkCancelJobs={onBulkCancelJobs}
            onBulkRequeueJobs={onBulkRequeueJobs}
            onCopyExport={onCopyExport}
            onDownloadExport={onDownloadExport}
          />
        )}
      />
    </section>
  );
}
