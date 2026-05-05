import { formatDuration, parseDate, toCsv, toDelimited } from "../format";
import { StatusPill } from "../components/StatusPill";
import type { JobRead } from "../types";

interface JobRow {
  id: string;
  job_id: string;
  title: string;
  status: string;
  age: string;
  time_in_status: string;
  assigned_worker_id: string;
  time_since_checkpoint: string;
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
  onRequeueJob: (job: JobRead) => void;
  loading: boolean;
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
  onRequeueJob,
  loading,
}: JobsViewProps) {
  const availableStatuses = Array.from(new Set(rows.map((job) => job.status))).sort();
  const filteredRows =
    selectedStatuses.length > 0
      ? rows.filter((row) => selectedStatuses.includes(row.status))
      : rows;
  const selectedJob = jobs.find((job) => job.id === selectedJobId) ?? jobs[0] ?? null;

  return (
    <div className="view-grid view-grid-jobs">
      <section className="panel panel-table">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Jobs</p>
            <h2>Execution queue</h2>
            <p className="panel-copy">Filter by status, inspect the active backlog, and act in context.</p>
          </div>
          <div className="toolbar">
            <button onClick={() => onCopyExport(toDelimited(filteredRows))} disabled={filteredRows.length === 0}>
              Copy TSV
            </button>
            <button
              className="secondary"
              onClick={() => onDownloadExport("relaymd-jobs.csv", toCsv(filteredRows), "text/csv")}
              disabled={filteredRows.length === 0}
            >
              Download CSV
            </button>
          </div>
        </div>

        <div className="filter-bar" aria-label="Job status filters">
          {availableStatuses.map((status) => (
            <label className="filter-chip" key={status}>
              <input
                type="checkbox"
                checked={selectedStatuses.includes(status)}
                onChange={(event) => onToggleStatus(status, event.target.checked)}
              />
              <span>{status}</span>
            </label>
          ))}
        </div>

        {loading ? <p className="panel-copy">Loading job data…</p> : null}
        {filteredRows.length === 0 ? (
          <div className="empty-state">
            <h3>No jobs in view</h3>
            <p>No jobs match the selected filters.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Age</th>
                  <th>Time In Status</th>
                  <th>Worker</th>
                  <th>Checkpoint</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => {
                  const backingJob = jobs.find((job) => job.id === row.id);
                  return (
                    <tr
                      className={selectedJob?.id === backingJob?.id ? "row-active" : ""}
                      key={row.id}
                    >
                      <td>
                        <button
                          className="row-link"
                          onClick={() => {
                            if (backingJob) {
                              onSelectJob(backingJob.id);
                            }
                          }}
                        >
                          <strong>{row.title}</strong>
                          <small>{row.job_id}</small>
                        </button>
                      </td>
                      <td>
                        <StatusPill tone={row.status as Parameters<typeof StatusPill>[0]["tone"]}>
                          {row.status}
                        </StatusPill>
                      </td>
                      <td>{row.age}</td>
                      <td>{row.time_in_status}</td>
                      <td>{row.assigned_worker_id}</td>
                      <td>{row.time_since_checkpoint}</td>
                      <td>
                        <div className="inline-actions">
                          {backingJob &&
                          (backingJob.status === "queued" ||
                            backingJob.status === "assigned" ||
                            backingJob.status === "running") ? (
                            <button className="danger-ghost" onClick={() => onCancelJob(backingJob)}>
                              Cancel
                            </button>
                          ) : null}
                          {backingJob && (backingJob.status === "failed" || backingJob.status === "cancelled") ? (
                            <button className="secondary" onClick={() => onRequeueJob(backingJob)}>
                              Re-queue
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <aside className="panel panel-detail">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Selected Job</p>
            <h2>{selectedJob?.title ?? "No job selected"}</h2>
          </div>
          {selectedJob ? (
            <StatusPill tone={selectedJob.status}>{selectedJob.status}</StatusPill>
          ) : null}
        </div>

        {selectedJob ? (
          <>
            <dl className="detail-list">
              <div>
                <dt>Job ID</dt>
                <dd>{selectedJob.id}</dd>
              </div>
              <div>
                <dt>Assigned Worker</dt>
                <dd>{selectedJob.assigned_worker_id || "-"}</dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>{parseDate(selectedJob.created_at)?.toISOString() ?? "-"}</dd>
              </div>
              <div>
                <dt>Updated</dt>
                <dd>{parseDate(selectedJob.updated_at)?.toISOString() ?? "-"}</dd>
              </div>
              <div>
                <dt>Input Bundle</dt>
                <dd>{selectedJob.input_bundle_path}</dd>
              </div>
              <div>
                <dt>Latest Checkpoint</dt>
                <dd>{selectedJob.latest_checkpoint_path || "-"}</dd>
              </div>
              <div>
                <dt>Checkpoint Age</dt>
                <dd>
                  {selectedJob.last_checkpoint_at
                    ? formatDuration(
                        (Date.now() - parseDate(selectedJob.last_checkpoint_at)!.getTime()) / 1000,
                      )
                    : "-"}
                </dd>
              </div>
            </dl>

            <div className="detail-actions">
              {(selectedJob.status === "queued" ||
                selectedJob.status === "assigned" ||
                selectedJob.status === "running") && (
                <button className="danger-ghost" onClick={() => onCancelJob(selectedJob)}>
                  Cancel job
                </button>
              )}
              {(selectedJob.status === "failed" || selectedJob.status === "cancelled") && (
                <button className="secondary" onClick={() => onRequeueJob(selectedJob)}>
                  Re-queue job
                </button>
              )}
            </div>
          </>
        ) : (
          <div className="empty-state">
            <h3>No selection</h3>
            <p>Select a job from the table to inspect identifiers, paths, and actions.</p>
          </div>
        )}
      </aside>
    </div>
  );
}
