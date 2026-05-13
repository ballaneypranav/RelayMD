import { useEffect, useMemo, useState } from "react";
import type { ColumnDef, Row } from "@tanstack/react-table";

import { ConsoleTable } from "../components/ConsoleTable";
import type { ClusterConfig } from "../types";

interface ClustersViewProps {
  clusters: ClusterConfig[];
  clusterEdits: Record<string, boolean>;
  unsavedCount: number;
  saveInFlight: boolean;
  onToggle: (clusterName: string, enabled: boolean) => void;
  onSave: () => void;
}

export function ClustersView({
  clusters,
  clusterEdits,
  unsavedCount,
  saveInFlight,
  onToggle,
  onSave,
}: ClustersViewProps) {
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>(["Enabled", "Disabled"]);
  const [selectedStrategies, setSelectedStrategies] = useState<string[]>([]);
  const [seenStrategies, setSeenStrategies] = useState<Set<string>>(new Set());

  const allStrategies = useMemo(() => {
    return Array.from(new Set(clusters.map((c) => c.strategy))).sort();
  }, [clusters]);

  useEffect(() => {
    const newStrategies = allStrategies.filter((s) => !seenStrategies.has(s));
    if (newStrategies.length > 0) {
      setSelectedStrategies((prev) => [...prev, ...newStrategies]);
      setSeenStrategies((prev) => new Set([...prev, ...newStrategies]));
    }
  }, [allStrategies, seenStrategies]);

  const filteredRows = useMemo(() => {
    return clusters.filter((cluster) => {
      const isEnabled = clusterEdits[cluster.name] ?? cluster.enabled;
      const statusLabel = isEnabled ? "Enabled" : "Disabled";
      if (!selectedStatuses.includes(statusLabel)) return false;
      if (selectedStrategies.length > 0 && !selectedStrategies.includes(cluster.strategy)) return false;
      return true;
    });
  }, [clusters, clusterEdits, selectedStatuses, selectedStrategies]);

  const columns = useMemo<ColumnDef<ClusterConfig>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Cluster",
        cell: ({ row }) => (
          <button className="row-link" onClick={() => row.toggleExpanded()} type="button">
            <strong>{row.original.name}</strong>
          </button>
        ),
      },
      {
        id: "enabled",
        header: "Enabled",
        cell: ({ row }) => {
          const isEnabled = clusterEdits[row.original.name] ?? row.original.enabled;
          return (
            <label className="toggle-label" style={{ margin: 0 }} onClick={(e) => e.stopPropagation()}>
              <input
                aria-label={`Toggle ${row.original.name} provisioning`}
                type="checkbox"
                checked={isEnabled}
                onChange={(event) => onToggle(row.original.name, event.target.checked)}
              />
              <span className="sr-only">{isEnabled ? "Enabled" : "Disabled"}</span>
            </label>
          );
        },
      },
      { accessorKey: "partition", header: "Partition" },
      { accessorKey: "strategy", header: "Strategy" },
      { accessorKey: "max_pending_jobs", header: "Max Pending Jobs" },
      { accessorKey: "wall_time", header: "Wall Time" },
      {
        id: "provisioning_state",
        header: "Provisioning State",
        accessorFn: (row) => ((clusterEdits[row.name] ?? row.enabled) ? "Enabled" : "Disabled"),
      },
    ],
    [clusterEdits, onToggle],
  );

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Clusters</p>
          <h2>Provisioning targets</h2>
          <p className="panel-copy">Review scheduling strategy, pending limits, and wall-clock constraints.</p>
        </div>
        <div className="toolbar">
          <span className="muted">{unsavedCount} unsaved changes</span>
          <button onClick={onSave} disabled={saveInFlight || unsavedCount === 0}>
            {saveInFlight ? "Saving..." : "Save changes"}
          </button>
        </div>
      </div>

      <ConsoleTable
        ariaLabel="Clusters table"
        columns={columns}
        data={filteredRows}
        emptyDescription="Configured SLURM clusters will appear here when the orchestrator exposes them."
        emptyTitle="No cluster configs available"
        enableSelection
        filterControls={
          <>
            <fieldset className="table-filter-group">
              <legend>Status</legend>
              {["Enabled", "Disabled"].map((status) => (
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
            {allStrategies.length > 0 && (
              <fieldset className="table-filter-group">
                <legend>Strategy</legend>
                {allStrategies.map((strategy) => (
                  <label className="table-menu-check" key={strategy}>
                    <input
                      checked={selectedStrategies.includes(strategy)}
                      onChange={(event) =>
                        setSelectedStrategies((current) =>
                          event.target.checked ? [...current, strategy] : current.filter((item) => item !== strategy),
                        )
                      }
                      type="checkbox"
                    />
                    <span>{strategy}</span>
                  </label>
                ))}
              </fieldset>
            )}
          </>
        }
        getRowId={(row) => row.name}
        initialPageSize={10}
        renderExpandedRow={(row: Row<ClusterConfig>) => {
          const cluster = row.original;
          const isEnabled = clusterEdits[cluster.name] ?? cluster.enabled;
          return (
            <div className="job-expanded-detail">
              <dl className="detail-list job-detail-grid">
                <div>
                  <dt>Cluster</dt>
                  <dd>{cluster.name}</dd>
                </div>
                <div>
                  <dt>Strategy</dt>
                  <dd>
                    <span className="cluster-badge">{cluster.strategy}</span>
                  </dd>
                </div>
                <div>
                  <dt>Provisioning</dt>
                  <dd>
                    <label className="toggle-label">
                      <input
                        aria-label={`Toggle ${cluster.name} provisioning`}
                        type="checkbox"
                        checked={isEnabled}
                        onChange={(event) => onToggle(cluster.name, event.target.checked)}
                      />
                      <span>{isEnabled ? "Enabled" : "Disabled"}</span>
                    </label>
                  </dd>
                </div>
                <div>
                  <dt>Partition</dt>
                  <dd>{cluster.partition}</dd>
                </div>
                <div>
                  <dt>Max Pending Jobs</dt>
                  <dd>{cluster.max_pending_jobs}</dd>
                </div>
                <div>
                  <dt>Wall Time</dt>
                  <dd>{cluster.wall_time}</dd>
                </div>
              </dl>
            </div>
          );
        }}
        searchPlaceholder="Search clusters"
      />
    </section>
  );
}
