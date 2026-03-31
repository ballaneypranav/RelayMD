import { StatusPill } from "../components/StatusPill";

interface WorkerRow {
  platform: string;
  gpu: string;
  provider_id: string;
  provider_state: string;
  uptime: string;
  last_heartbeat: string;
  current_job: string;
  status: string;
}

interface WorkersViewProps {
  rows: WorkerRow[];
  onCopyExport: (text: string) => void;
  onDownloadExport: (filename: string, text: string, mime: string) => void;
  toDelimited: (rows: WorkerRow[]) => string;
  toCsv: (rows: WorkerRow[]) => string;
}

export function WorkersView({
  rows,
  onCopyExport,
  onDownloadExport,
  toDelimited: asDelimited,
  toCsv: asCsv,
}: WorkersViewProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Workers</p>
          <h2>Fleet health</h2>
          <p className="panel-copy">Track active capacity, queued allocations, and stale nodes.</p>
        </div>
        <div className="toolbar">
          <button onClick={() => onCopyExport(asDelimited(rows))} disabled={rows.length === 0}>
            Copy TSV
          </button>
          <button
            className="secondary"
            onClick={() => onDownloadExport("relaymd-workers.csv", asCsv(rows), "text/csv")}
            disabled={rows.length === 0}
          >
            Download CSV
          </button>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="empty-state">
          <h3>No workers registered</h3>
          <p>Worker data will appear here after the first worker registration heartbeat.</p>
        </div>
      ) : (
        <div className="worker-grid">
          {rows.map((worker) => (
            <article className={`worker-card worker-${worker.status}`} key={`${worker.platform}-${worker.provider_id}-${worker.current_job}`}>
              <div className="worker-card-head">
                <div>
                  <p className="eyebrow">{worker.platform}</p>
                  <h3>{worker.gpu}</h3>
                </div>
                <StatusPill tone={worker.status as Parameters<typeof StatusPill>[0]["tone"]}>
                  {worker.status}
                </StatusPill>
              </div>
              <dl className="detail-list compact">
                <div>
                  <dt>Provider ID</dt>
                  <dd>{worker.provider_id}</dd>
                </div>
                <div>
                  <dt>Provider State</dt>
                  <dd>{worker.provider_state}</dd>
                </div>
                <div>
                  <dt>Uptime</dt>
                  <dd>{worker.uptime}</dd>
                </div>
                <div>
                  <dt>Last Heartbeat</dt>
                  <dd>{worker.last_heartbeat}</dd>
                </div>
                <div>
                  <dt>Current Job</dt>
                  <dd>{worker.current_job}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
