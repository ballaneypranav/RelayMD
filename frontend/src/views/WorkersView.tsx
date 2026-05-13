import { useMemo, useState } from "react";
import type { ColumnDef, Row } from "@tanstack/react-table";

import { ConsoleTable, type ConsoleTableToolbarContext } from "../components/ConsoleTable";
import { parseDate, toCsv, toDelimited, truncateUuid, type WorkerRow } from "../format";
import { StatusPill } from "../components/StatusPill";
import type { WorkerRead } from "../types";

interface WorkersViewProps {
  rows: WorkerRow[];
  workers: WorkerRead[];
  onCopyExport: (text: string) => void;
  onDownloadExport: (filename: string, text: string, mime: string) => void;
  toDelimited: (rows: WorkerRow[]) => string;
  toCsv: (rows: WorkerRow[]) => string;
}

interface WorkerTableRow extends WorkerRow {
  worker: WorkerRead | null;
  worker_id_full: string;
  provider_raw_state: string;
  provider_reason: string;
  provider_last_checked: string;
  registered_at: string;
  heartbeat_timestamp: string;
}

const STATUS_FILTERS = ["active", "provisioning", "stale"] as const;

function WorkerExpandedDetails({ row }: { row: WorkerTableRow }) {
  const worker = row.worker;

  return (
    <div className="job-expanded-detail">
      <dl className="detail-list job-detail-grid">
        <div>
          <dt>Worker ID</dt>
          <dd>{worker?.id ?? row.id}</dd>
        </div>
        <div>
          <dt>Provider ID</dt>
          <dd>{worker?.provider_id || row.provider_id || "-"}</dd>
        </div>
        <div>
          <dt>Provider Raw State</dt>
          <dd>{worker?.provider_state_raw || "-"}</dd>
        </div>
        <div>
          <dt>Provider Reason</dt>
          <dd>{worker?.provider_reason || "-"}</dd>
        </div>
        <div>
          <dt>Provider Last Checked</dt>
          <dd>{parseDate(worker?.provider_last_checked_at)?.toISOString() ?? "-"}</dd>
        </div>
        <div>
          <dt>Registered</dt>
          <dd>{parseDate(worker?.registered_at)?.toISOString() ?? "-"}</dd>
        </div>
        <div>
          <dt>Heartbeat Timestamp</dt>
          <dd>{parseDate(worker?.last_heartbeat)?.toISOString() ?? "-"}</dd>
        </div>
        <div>
          <dt>Current Job</dt>
          <dd>{row.current_job || "-"}</dd>
        </div>
      </dl>
    </div>
  );
}

function WorkersToolbar({
  context,
  onCopyExport,
  onDownloadExport,
}: {
  context: ConsoleTableToolbarContext<WorkerTableRow>;
  onCopyExport: (text: string) => void;
  onDownloadExport: (filename: string, text: string, mime: string) => void;
}) {
  const exportRows = context.table
    .getFilteredRowModel()
    .rows.map((row) => row.original)
    .map(({ worker, ...rest }) => rest);

  return (
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
          onClick={() => onDownloadExport("relaymd-workers.csv", toCsv(exportRows), "text/csv")}
          type="button"
        >
          Download CSV
        </button>
      </div>
    </details>
  );
}

export function WorkersView({
  rows,
  workers,
  onCopyExport,
  onDownloadExport,
  toDelimited: _asDelimited,
  toCsv: _asCsv,
}: WorkersViewProps) {
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([...STATUS_FILTERS]);
  const workerById = useMemo(() => new Map(workers.map((worker) => [worker.id, worker])), [workers]);

  const filteredRows =
    selectedStatuses.length > 0
      ? rows.filter((row) => selectedStatuses.includes(row.status))
      : [];

  const tableRows = useMemo<WorkerTableRow[]>(
    () =>
      filteredRows.map((row) => {
        const worker = workerById.get(row.id) ?? null;
        return {
          ...row,
          worker,
          worker_id_full: worker?.id ?? row.id,
          provider_raw_state: worker?.provider_state_raw || "-",
          provider_reason: worker?.provider_reason || "-",
          provider_last_checked: parseDate(worker?.provider_last_checked_at)?.toISOString() ?? "-",
          registered_at: parseDate(worker?.registered_at)?.toISOString() ?? "-",
          heartbeat_timestamp: parseDate(worker?.last_heartbeat)?.toISOString() ?? "-",
        };
      }),
    [filteredRows, workerById],
  );

  const columns = useMemo<ColumnDef<WorkerTableRow>[]>(
    () => [
      {
        accessorKey: "id",
        header: "Worker ID",
        cell: ({ row }) => (
          <button className="row-link" onClick={() => row.toggleExpanded()} type="button">
            <strong>{truncateUuid(row.original.id)}</strong>
          </button>
        ),
      },
      { accessorKey: "worker_id_full", header: "Worker ID (Full)" },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <StatusPill tone={row.original.status as Parameters<typeof StatusPill>[0]["tone"]}>
            {row.original.status}
          </StatusPill>
        ),
      },
      { accessorKey: "platform", header: "Platform" },
      { accessorKey: "gpu", header: "GPU" },
      { accessorKey: "provider_id", header: "Provider ID" },
      { accessorKey: "provider_state", header: "Provider State" },
      { accessorKey: "provider_raw_state", header: "Provider Raw State" },
      { accessorKey: "provider_reason", header: "Provider Reason" },
      { accessorKey: "provider_last_checked", header: "Provider Last Checked" },
      { accessorKey: "registered_at", header: "Registered" },
      { accessorKey: "heartbeat_timestamp", header: "Heartbeat Timestamp" },
      { accessorKey: "current_job", header: "Current Job" },
      { accessorKey: "uptime", header: "Uptime" },
      { accessorKey: "last_heartbeat", header: "Last Heartbeat" },
    ],
    [],
  );

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Workers</p>
          <h2>Fleet health</h2>
          <p className="panel-copy">Track active capacity, queued allocations, and stale nodes.</p>
        </div>
      </div>

      <ConsoleTable
        ariaLabel="Workers table"
        columns={columns}
        data={tableRows}
        emptyDescription="Worker data will appear here after the first worker registration heartbeat."
        emptyTitle="No workers registered"
        enableSelection
        filterControls={
          <fieldset className="table-filter-group">
            <legend>Status</legend>
            {STATUS_FILTERS.map((status) => (
              <label className="table-menu-check" key={status}>
                <input
                  checked={selectedStatuses.includes(status)}
                  onChange={(event) =>
                    setSelectedStatuses((current) =>
                      event.target.checked ? [...current, status] : current.filter((item) => item !== status),
                    )
                  }
                  type="checkbox"
                />
                <span>{status}</span>
              </label>
            ))}
          </fieldset>
        }
        getRowId={(row) => row.id}
        initialPageSize={10}
        initialColumnVisibility={{
          worker_id_full: false,
          provider_raw_state: false,
          provider_reason: false,
          provider_last_checked: false,
          registered_at: false,
          heartbeat_timestamp: false,
        }}
        renderExpandedRow={(row: Row<WorkerTableRow>) => <WorkerExpandedDetails row={row.original} />}
        searchPlaceholder="Search workers"
        toolbarActions={(context) => (
          <WorkersToolbar
            context={context}
            onCopyExport={onCopyExport}
            onDownloadExport={onDownloadExport}
          />
        )}
      />
    </section>
  );
}
